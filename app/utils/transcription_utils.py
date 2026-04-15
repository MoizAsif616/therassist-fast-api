import os
import asyncio
import httpx
import re
import statistics
import json
from fastapi import HTTPException
from loguru import logger
from app.core.supabase_client import db
from app.utils.promt_templates import (
    CLINICAL_PROFILE_PROMPT, 
    SESSION_SUMMARY_PROMPT, 
    SENTIMENT_ANALYSIS_PROMPT, 
    THEME_EXTRACTION_PROMPT, 
    SPEAKER_IDENTIFICATION_PROMPT
)

# --- MODEL & KEY CONFIGURATION ---
MODEL1_NAME = os.getenv("MODEL1_NAME")
MODEL2_NAME = os.getenv("MODEL2_NAME")
MODEL3_NAME = os.getenv("MODEL3_NAME")

KEY1 = os.getenv("MODEL_API_KEY_1")
KEY2 = os.getenv("MODEL_API_KEY_2")
KEY3 = os.getenv("MODEL_API_KEY_3")

SENTIMENT_MODEL_NAME = os.getenv("SENTIMENT_MODEL_NAME")
SENTIMENT_MODEL_KEY = os.getenv("SENTIMENT_MODEL_KEY")

MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))

# API Endpoints
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
CEREBRAS_CHAT_URL = "https://api.cerebras.ai/v1/chat/completions"

async def _call_llm_api(
    messages: list, 
    model: str,
    api_key: str,
    json_mode: bool = False, 
    temperature: float = 0.0,
    timeout: float = 60.0
) -> str:
    """
    Robust HTTPX call to Groq with Exponential Backoff and specific API Key usage.
    """
    if not api_key:
        logger.error(f"[_call_llm_api] API Key is missing for model {model}")
        raise HTTPException(status_code=500, detail=f"[_call_llm_api] Configuration Error: API Key for {model} is missing.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False
    }
    
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    for attempt in range(MAX_RETRIES):
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                resp = await client.post(GROQ_CHAT_URL, headers=headers, json=payload)
                
                if resp.status_code == 429:
                    wait_time = (attempt * 5) + 5 
                    logger.warning(f"[_call_llm_api] Rate Limit (429) on {model}. Retrying in {wait_time}s... (Attempt {attempt+1}/{MAX_RETRIES})")
                    await asyncio.sleep(wait_time)
                    continue
                
                if resp.status_code >= 500:
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(2)
                        continue
                    raise HTTPException(status_code=502, detail=f"[_call_llm_api] Upstream Service Error: {resp.status_code} from Groq.")

                resp.raise_for_status()
                result = resp.json()
                
                if not result.get("choices"):
                    raise HTTPException(status_code=502, detail=f"[_call_llm_api] Groq Error: Empty choices returned for model {model}.")

                content = result["choices"][0]["message"]["content"]
                
                if "<think>" in content:
                    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                
                return content
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    continue
                status = 401 if e.response.status_code == 401 else 502
                raise HTTPException(status_code=status, detail=f"[_call_llm_api] HTTP Error {e.response.status_code}")
            
            except httpx.RequestError as e:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(3)
                    continue
                raise HTTPException(status_code=504, detail=f"[_call_llm_api] Connection Failed: {str(e)}")
            
            except Exception as e:
                if isinstance(e, HTTPException): raise e
                raise HTTPException(status_code=500, detail=f"[_call_llm_api] Unexpected Error: {str(e)}")

    raise HTTPException(status_code=503, detail=f"[_call_llm_api] Rate Limit Exhausted after {MAX_RETRIES} attempts.")

# --- TASK DISTRIBUTION ---

async def generate_summary(session_number: int, utterances: list) -> str:
    """Uses MODEL 2 (Key 2)"""
    text = format_transcript_for_llm(utterances)
    messages = [
        {"role": "system", "content": "You summarize therapy sessions professionally."},
        {"role": "user", "content": SESSION_SUMMARY_PROMPT.format(transcription_text=text, session_number=session_number)},
    ]
    try:
        logger.info(f"[TRANSCRIPTION UTILS] [SUMMARY] Using {MODEL2_NAME} (Key 2)")
        summary = await _call_llm_api(messages, model=MODEL2_NAME, api_key=KEY2, timeout=120.0)
        logger.success(f"[TRANSCRIPTION UTILS] [SUMMARY] Generated successfully ({len(summary)} chars).")
        return summary.strip()
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"[generate_summary] Failed: {str(e)}")

async def generate_theme(session_number: int, utterances: list) -> dict:
    """Uses MODEL 3 (Key 3)"""
    text = format_transcript_for_llm(utterances)
    messages = [
        {"role": "system", "content": "You are a clinical classification assistant."},
        {"role": "user", "content": THEME_EXTRACTION_PROMPT.format(transcription_text=text)},
    ]
    try:
        logger.info(f"[TRANSCRIPTION UTILS] [SESSION THEME] Using {MODEL3_NAME} (Key 3)")
        content = await _call_llm_api(messages, model=MODEL3_NAME, api_key=KEY3, temperature=0.1, timeout=45.0)
        
        theme_match = re.search(r"THEME:\s*(.+)", content)
        explanation_match = re.search(r"EXPLANATION:\s*(.+)", content)
        
        if not theme_match: 
            raise HTTPException(502, detail=f"[generate_theme] AI response missing mandatory 'THEME:' tag.")
        
        logger.success(f"[TRANSCRIPTION UTILS] [SESSION THEME] Theme extracted successfully.")
        return {
            "theme": theme_match.group(1).strip(),
            "explanation": explanation_match.group(1).strip() if explanation_match else "No explanation."
        }
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"[generate_theme] Failed: {str(e)}")

async def _call_cerebras_api(
    messages: list, 
    model: str,
    api_key: str,
    json_mode: bool = False, 
    temperature: float = 0.0,
    timeout: float = 60.0
) -> str:
    """
    Dedicated HTTPX call to Cerebras API with Exponential Backoff.
    """
    if not api_key:
        logger.error(f"[_call_cerebras_api] API Key is missing for model {model}")
        raise HTTPException(status_code=500, detail=f"[_call_cerebras_api] Configuration Error: API Key for {model} is missing.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False
    }
    
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    for attempt in range(MAX_RETRIES):
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                resp = await client.post(CEREBRAS_CHAT_URL, headers=headers, json=payload)
                
                if resp.status_code == 429:
                    wait_time = (attempt * 5) + 5 
                    logger.warning(f"[_call_cerebras_api] Rate Limit (429) on {model}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                
                if resp.status_code >= 500:
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(2)
                        continue
                    raise HTTPException(status_code=502, detail=f"[_call_cerebras_api] Upstream Error: {resp.status_code} from Cerebras.")

                resp.raise_for_status()
                result = resp.json()
                
                if not result.get("choices"):
                    raise HTTPException(status_code=502, detail=f"[_call_cerebras_api] Cerebras Error: Empty choices returned.")

                content = result["choices"][0]["message"]["content"]
                
                if "<think>" in content:
                    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                
                return content
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    continue
                status = 401 if e.response.status_code == 401 else 502
                raise HTTPException(status_code=status, detail=f"[_call_cerebras_api] HTTP Error {e.response.status_code}")
            
            except httpx.RequestError as e:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(3)
                    continue
                raise HTTPException(status_code=504, detail=f"[_call_cerebras_api] Connection Failed: {str(e)}")
            
            except Exception as e:
                if isinstance(e, HTTPException): raise e
                raise HTTPException(status_code=500, detail=f"[_call_cerebras_api] Unexpected Error: {str(e)}")

    raise HTTPException(status_code=503, detail=f"[_call_cerebras_api] Rate Limit Exhausted after {MAX_RETRIES} attempts.")

def _format_chunk_for_sentiment(utterances: list) -> str:
    """Formats transcript chunk with minimal tokens (removes colons etc)"""
    lines = []
    for u in utterances:
        speaker = u.get("speaker", "Unknown")
        text = u.get("text", "").strip()
        lines.append(f"{speaker} {text}")
    return "\n".join(lines)

async def _fetch_chunk_sentiment(chunk_utterances: list, previous_context: str) -> float:
    text = _format_chunk_for_sentiment(chunk_utterances)
    messages = [
        {"role": "system", "content": "You are a clinical sentiment analyzer."},
        {"role": "user", "content": SENTIMENT_ANALYSIS_PROMPT.format(
            previous_context_text=previous_context if previous_context else "None",
            current_chunk_text=text
        )}
    ]
    try:
        content = await _call_cerebras_api(
            messages, 
            model=SENTIMENT_MODEL_NAME, 
            api_key=SENTIMENT_MODEL_KEY, 
            json_mode=True,
            temperature=0.1, 
            timeout=45.0
        )
        
        if "```json" in content:
            match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
            clean_json = match.group(1) if match else content
        else:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            clean_json = match.group(0) if match else content
            
        data = json.loads(clean_json)
        score = float(data.get("score", 0.0))
        return max(-1.0, min(1.0, score))
    except Exception as e:
        logger.error(f"[_fetch_chunk_sentiment] Failed: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to score chunk: {e}")

async def generate_sentiment(session_id: str, utterances: list) -> float:
    """
    Divides session into 10-minute chunks and calculates a weighted final score.
    Uses Cerebras model sequentially for each chunk.
    """
    try:
        chunk_duration_sec = 600.0
        chunks = []
        current_chunk = []
        chunk_start_time = None
        
        for u in utterances:
            t_sec = _parse_timestamp_to_seconds(u.get("start_time") or u.get("start"))
            if chunk_start_time is None:
                chunk_start_time = t_sec
                current_chunk.append(u)
            else:
                if t_sec - chunk_start_time <= chunk_duration_sec:
                    current_chunk.append(u)
                else:
                    chunks.append(current_chunk)
                    current_chunk = [u]
                    chunk_start_time = t_sec
                    
        if current_chunk:
            chunks.append(current_chunk)

        total_chunks = len(chunks)
        logger.info(f"[TRANSCRIPTION UTILS] [SENTIMENT] Split session into {total_chunks} chunks.")
        
        if total_chunks == 0:
            return 0.0

        scores = []
        previous_context = ""
        
        # Sequentially score each chunk
        for i, chunk in enumerate(chunks, start=1):
            score = await _fetch_chunk_sentiment(chunk, previous_context)
            scores.append(score)
            logger.info(f"[TRANSCRIPTION UTILS] [SENTIMENT] Chunk {i}/{total_chunks} score: {score:.2f}")
            
            # Prepare context for next chunk (last 3 utterances)
            if len(chunk) > 3:
                previous_context = _format_chunk_for_sentiment(chunk[-3:])
            else:
                previous_context = _format_chunk_for_sentiment(chunk)

        if not scores:
            raise HTTPException(502, detail="[generate_sentiment] No scores returned.")

        avg_score = statistics.mean(scores)
        peak_score = max(scores, key=lambda x: abs(x))
        last_score = scores[-1]
        
        # Standard Average (40%) + Heaviest Peak (40%) + Ending State (20%)
        final_score = (avg_score * 0.4) + (peak_score * 0.4) + (last_score * 0.2)
        final_score = max(-1.0, min(1.0, final_score))
        
        logger.success(f"[TRANSCRIPTION UTILS] [SENTIMENT] Final weighted score: {final_score:.2f} (Avg: {avg_score:.2f}, Peak: {peak_score:.2f}, Last: {last_score:.2f})")
        return final_score

    except Exception as e:
        if isinstance(e, HTTPException): raise e
        logger.error(f"[generate_sentiment] Failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"[generate_sentiment] Failed: {str(e)}")

async def generate_clinical_profile(client_id: str, session_number: int, utterances: list) -> str:
    """Uses MODEL 3 (Key 3)"""
    existing_history = "No prior history."
    try:
        resp = db()("client_insights").select("clinical_profile").eq("client_id", client_id).maybe_single().execute()
        if resp and resp.data and resp.data.get("clinical_profile"):
            existing_history = resp.data["clinical_profile"]
    except Exception as e:
        logger.error(f"[generate_clinical_profile] DB History Fetch Failed: {e}")

    transcript_text = format_transcript_for_llm(utterances)
    final_prompt = CLINICAL_PROFILE_PROMPT.format(
        existing_profile_history=existing_history,
        session_number=session_number,
        transcription_text=transcript_text
    )

    messages = [
        {"role": "system", "content": "You are a clinical supervisor."},
        {"role": "user", "content": final_prompt},
    ]

    try:
        logger.info(f"[TRANSCRIPTION UTILS] [PROFILE] Using {MODEL3_NAME} (Key 3)")
        content = await _call_llm_api(messages, model=MODEL3_NAME, api_key=KEY3, temperature=0.3, timeout=120.0)
        logger.success(f"[TRANSCRIPTION UTILS] [PROFILE] Clinical Profile updated ({len(content)} chars).")
        return content.strip()
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"[generate_clinical_profile] Failed: {str(e)}")

async def identify_speaker_roles(utterances: list) -> dict:
    """Uses MODEL 1 (Key 1)"""
    lines = [f"Speaker {u.get('speaker', 'Unknown')}: {u.get('text', '')}" for u in utterances]
    sample_text = "\n".join(lines)
    final_prompt = SPEAKER_IDENTIFICATION_PROMPT.format(transcript_sample=sample_text)

    messages = [{"role": "user", "content": final_prompt}]

    try:
        logger.info(f"[TRANSCRIPTION UTILS] [ROLE_ID] Using {MODEL1_NAME} (Key 1)")
        content = await _call_llm_api(messages, model=MODEL1_NAME, api_key=KEY1, json_mode=True, temperature=0.1, timeout=30.0)

        if "```json" in content:
            match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
            clean_json = match.group(1) if match else content
        else:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            clean_json = match.group(0) if match else content

        data = json.loads(clean_json)
        final_map = {}
        v_t = str(data.get("Therapist", "")).replace("Speaker ", "").strip()
        v_c = str(data.get("Client", "")).replace("Speaker ", "").strip()
        
        if v_t: final_map[v_t] = "Therapist"
        if v_c: final_map[v_c] = "Client"
        
        logger.success(f"[TRANSCRIPTION UTILS] [ROLE_ID] Successfully mapped speaker roles.")
        return final_map
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"[identify_speaker_roles] Failed: {str(e)}")

# --- UTILITY HELPERS ---

def format_transcript_for_llm(utterances: list) -> str:
    """
    Converts a list of utterance dictionaries into a clean, token-efficient string.
    Format: Turn #[Seq] [Speaker]: [Text]
    """
    if not utterances:
        return "No transcript available."
    
    formatted_lines = []
    for i, u in enumerate(utterances, start=1):
        speaker = u.get("speaker", "Unknown")
        text = u.get("text", "").strip()
        formatted_lines.append(f"Turn #{i} [{speaker}]: {text}")
    
    return "\n".join(formatted_lines)

def _parse_timestamp_to_seconds(timestamp_str: str) -> float:
    if not timestamp_str: return 0.0
    try:
        parts = list(map(float, str(timestamp_str).split(':')))
        if len(parts) == 3: return parts[0] * 3600 + parts[1] * 60 + parts[2]
        if len(parts) == 2: return parts[0] * 60 + parts[1]
        return float(parts[0])
    except:
        return 0.0

async def impute_speaker_labels(cleaned_data: dict, role_map: dict) -> dict:
    try:
        if not isinstance(cleaned_data, dict) or "utterances" not in cleaned_data:
            raise HTTPException(status_code=422, detail="Invalid input format.")
        
        if not role_map: return cleaned_data

        updated_utterances = []
        for i, u in enumerate(cleaned_data["utterances"], start=1):
            original = u.get("speaker")
            new_u = u.copy()
            new_u["speaker"] = role_map.get(original, original)
            new_u["sequence_number"] = i
            
            r_s = u.get("start") or u.get("start_time")
            r_e = u.get("end") or u.get("end_time")
            new_u["start_seconds"] = _parse_timestamp_to_seconds(r_s)
            new_u["end_seconds"] = _parse_timestamp_to_seconds(r_e)
            updated_utterances.append(new_u)

        result = cleaned_data.copy()
        result["utterances"] = updated_utterances
        return result
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"[impute_speaker_labels] Failed: {str(e)}")
