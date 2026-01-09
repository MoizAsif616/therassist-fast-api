import os
import asyncio
import httpx
import re
import statistics
from fastapi import HTTPException
from loguru import logger
from app.core.supabase_client import db
from app.utils.promt_templates import CLINICAL_PROFILE_PROMPT, SESSION_SUMMARY_PROMPT, SENTIMENT_ANALYSIS_PROMPT, THEME_EXTRACTION_PROMPT, SPEAKER_IDENTIFICATION_PROMPT

# --- MODEL CONFIGURATION ---
MODEL1_NAME = os.getenv("MODEL1_NAME")
MODEL1_KEY = os.getenv("MODEL1_API_KEY")

MODEL2_NAME = os.getenv("MODEL2_NAME")
MODEL2_KEY = os.getenv("MODEL2_API_KEY")

MODEL3_NAME = os.getenv("MODEL3_NAME")
MODEL3_KEY = os.getenv("MODEL3_API_KEY")

MAX_RETRIES = int(os.getenv("MAX_RETRIES", 1))

# --------------------------------------------------------------
# 1. SUMMARY GENERATION
# --------------------------------------------------------------
async def generate_summary(session_id: str, text: str) -> str:
    if not MODEL2_KEY:
        raise HTTPException(500, detail="Server misconfiguration: MODEL1_API_KEY missing.")

    headers = {
        "Authorization": f"Bearer {MODEL2_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
    }
    payload = {
        "model": MODEL2_NAME,
        "messages": [
            {"role": "system", "content": "You summarize therapy sessions professionally."},
            {"role": "user", "content": SESSION_SUMMARY_PROMPT.format(transcription_text=text)},
        ]
    }

    try:
        logger.info(f"[TRANSCRIPTION UTILS] [SUMMARY] Generating summary for Session {session_id}...")
        
        # --- ADDED RETRY LOOP (3 Attempts) ---
        max_retries = MAX_RETRIES
        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(trust_env=False) as client:
                    resp = await client.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers, timeout=120)
                    
                    if resp.status_code != 200:
                        # Check if we should retry
                        if attempt < max_retries:
                            await asyncio.sleep(2 * attempt) # Wait 2s, 4s...
                            continue
                        
                        # Only log error and raise on FINAL attempt
                        logger.error(f"[TRANSCRIPTION UTILS] [SUMMARY] Upstream Error: {resp.text}")
                        raise HTTPException(502, detail=f"Summary Failed: {resp.status_code}")

                summary = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if not summary: 
                    if attempt < max_retries:
                        await asyncio.sleep(2 * attempt)
                        continue

                    logger.error(f"[TRANSCRIPTION UTILS] [SUMMARY] Empty response from AI.")
                    raise HTTPException(502, detail="Summary AI returned empty response.")
                
                logger.success(f"[TRANSCRIPTION UTILS] [SUMMARY] Generated successfully ({len(summary)} chars).")
                return summary

            except Exception as e:
                # Catch network/timeout errors during retry loop
                if attempt < max_retries:
                    await asyncio.sleep(2 * attempt)
                    logger.warning(f"[TRANSCRIPTION UTILS] [SUMMARY] Attempt {attempt} failed: {e}")
                    continue
                # If final attempt failed, re-raise to be caught by outer block
                raise e

    except Exception as e:
        logger.error(f"[TRANSCRIPTION UTILS] Exception: {e}")
        raise HTTPException(502, detail=f"Summary Error: {e}")


# --------------------------------------------------------------
# 2. THEME EXTRACTION
# --------------------------------------------------------------
async def generate_theme(session_id: str, text: str) -> dict:
    if not MODEL3_KEY:
        raise HTTPException(500, detail="MODEL3_API_KEY missing.")

    headers = {"Authorization": f"Bearer {MODEL3_KEY}", "Content-Type": "application/json", "HTTP-Referer": "http://localhost"}
    payload = {
        "model": MODEL3_NAME,
        "messages": [
            {"role": "system", "content": "You are a clinical classification assistant."},
            {"role": "user", "content": THEME_EXTRACTION_PROMPT.format(transcription_text=text)},
        ],
        "temperature": 0.1, 
    }

    try:
        logger.info(f"[TRANSCRIPTION UTILS] [SESSION THEME] Extracting theme for Session {session_id}...")
        
        # --- ADDED RETRY LOOP (3 Attempts) ---
        max_retries = MAX_RETRIES
        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(trust_env=False) as client:
                    resp = await client.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers, timeout=45)
                    
                    if resp.status_code != 200:
                        if attempt < max_retries:
                            logger.warning(f"[TRANSCRIPTION UTILS] [SESSION THEME] Upstream Error {resp.status_code} (Attempt {attempt}). Retrying...")
                            await asyncio.sleep(2 * attempt)
                            continue
                            
                        logger.error(f"[TRANSCRIPTION UTILS] [SESSION THEME] Upstream Error: {resp.text}")
                        raise HTTPException(502, detail=f"Theme Failed: {resp.status_code}")
                    
                content = resp.json()["choices"][0]["message"]["content"]
                theme_match = re.search(r"THEME:\s*(.+)", content)
                explanation_match = re.search(r"EXPLANATION:\s*(.+)", content)
                
                if not theme_match: 
                    if attempt < max_retries:
                        logger.warning(f"[TRANSCRIPTION UTILS] [SESSION THEME] Missing THEME tag (Attempt {attempt}). Retrying...")
                        await asyncio.sleep(2 * attempt)
                        continue

                    logger.error(f"[TRANSCRIPTION UTILS] [SESSION THEME] Missing THEME tag in response: {content}")
                    raise HTTPException(502, detail="AI response missing 'THEME:' tag.")
                
                logger.success(f"[TRANSCRIPTION UTILS] [SESSION THEME] Theme extracted successfully.")
                return {
                    "theme": theme_match.group(1).strip(),
                    "explanation": explanation_match.group(1).strip() if explanation_match else "No explanation."
                }

            except Exception as e:
                # Catch network/timeout errors during retry loop
                if attempt < max_retries:
                    logger.warning(f"[TRANSCRIPTION UTILS] [SESSION THEME] Attempt {attempt} failed: {e}. Retrying...")
                    await asyncio.sleep(2 * attempt)
                    continue
                # Re-raise on final attempt so the outer block catches it
                raise e

    except Exception as e:
        logger.error(f"[TRANSCRIPTION UTILS] Exception: {e}")
        raise HTTPException(502, detail=f"Theme Error: {e}")


# --------------------------------------------------------------
# 3. SENTIMENT ANALYSIS (Parallel)
# --------------------------------------------------------------
async def _fetch_single_sentiment(model_name: str, api_key: str, text: str) -> float | None:
    if not api_key: return None
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "HTTP-Referer": "http://localhost"}
    payload = {
        "model": model_name,
        "messages": [{"role": "system", "content": "You are a clinical sentiment analyzer."}, {"role": "user", "content": SENTIMENT_ANALYSIS_PROMPT.format(transcription_text=text)}],
        "temperature": 0.1,
    }
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            resp = await client.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers, timeout=30)
            if resp.status_code != 200: return None
            
        match = re.search(r"SENTIMENT_SCORE:\s*([-+]?\d*\.\d+|\d+)", resp.json()["choices"][0]["message"]["content"])
        return max(-1.0, min(1.0, float(match.group(1)))) if match else None
    except: return None

async def generate_sentiment(session_id: str, text: str) -> float:
      
    try:
      logger.info(f"[TRANSCRIPTION UTILS] [SENTIMENT] Generating sentiment for Session {session_id}...")
      tasks = [
          _fetch_single_sentiment(MODEL1_NAME, MODEL1_KEY, text),
          _fetch_single_sentiment(MODEL2_NAME, MODEL2_KEY, text),
          _fetch_single_sentiment(MODEL3_NAME, MODEL3_KEY, text)
      ]
      results = await asyncio.gather(*tasks)
    except Exception as e:
      logger.error(f"[TRANSCRIPTION UTILS] [SENTIMENT] Exception: {e}")
      raise HTTPException(502, detail=f"Sentiment Analysis Failed: {e}")
    
    valid = [r for r in results if r is not None]
    
    if not valid:
        logger.error("[TRANSCRIPTION UTILS] All 3 sentiment models failed.")
        raise HTTPException(502, detail="Sentiment Analysis Failed: All AI models returned errors.")

    logger.success(f"[TRANSCRIPTION UTILS] Sentiment scores generated: {valid}")
    return statistics.mean(valid)

async def generate_clinical_profile(client_id: str, session_number: int, transcript_text: str) -> str:
    """
    Generates an updated Clinical Profile using Model 1.
    Includes DB fetching, Prompt formatting, and Retries (Max 2).
    """

    # --- 1. Fetch Existing Profile (Context) ---
    logger.info(f"[TRANSCRIPTION UTILS] [PROFILE] Fetching history for Client {client_id}...")
    existing_history = "No prior history. This is the Initial Assessment (Session 1)."

    try:
        resp = db()("client_insights")\
            .select("clinical_profile")\
            .eq("client_id", client_id)\
            .maybe_single()\
            .execute()
        
        if resp and resp.data and resp.data.get("clinical_profile"):
            fetched_profile = resp.data["clinical_profile"]
            # Basic check to ensure it's not just an empty string
            if len(fetched_profile) > 10:
                existing_history = fetched_profile
                logger.info("[TRANSCRIPTION UTILS] [PROFILE] Found existing history.")
            else:
                logger.info("[TRANSCRIPTION UTILS] [PROFILE] History too short, treating as new.")
        else:
            logger.info("[TRANSCRIPTION UTILS] [PROFILE] No history found (Session 1).")
            
    except Exception as e:
        logger.error(f"[TRANSCRIPTION UTILS] [PROFILE] DB Read Error : {e}")
        raise HTTPException(500, detail="Database fetch failed while reading the clinical profile.")

    # --- 2. Prepare Prompt ---
    final_prompt = CLINICAL_PROFILE_PROMPT.format(
        existing_profile_history=existing_history,
        session_number=session_number,
        transcription_text=transcript_text # Safety truncate
    )

    # --- 3. Setup Request ---
    if not MODEL3_KEY:
        raise HTTPException(500, detail="MODEL3_API_KEY missing.")

    headers = {
        "Authorization": f"Bearer {MODEL3_KEY}", 
        "Content-Type": "application/json", 
        "HTTP-Referer": "http://localhost"
    }
    
    payload = {
        "model": MODEL3_NAME,
        "messages": [
            {"role": "system", "content": "You are a clinical supervisor."},
            {"role": "user", "content": final_prompt},
        ],
        "temperature": 0.3, 
        "max_tokens": 20000
    }

    # --- 4. Call LLM (With 2 Retries) ---
    max_retries = MAX_RETRIES
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"[TRANSCRIPTION UTILS] [PROFILE] Generating Profile (Attempt {attempt}/{max_retries})...")
            
            async with httpx.AsyncClient(trust_env=False) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions", 
                    json=payload, 
                    headers=headers, 
                    timeout=60 # Slightly longer timeout for "Thinking" models
                )
                
                if resp.status_code != 200:
                    logger.error(f"[TRANSCRIPTION UTILS] [PROFILE] Upstream Error: {resp.text}")
                    # Force a retry by raising an exception
                    raise Exception(f"Status {resp.status_code}")

                content = resp.json()["choices"][0]["message"]["content"]
                
                if not content:
                    raise Exception("Empty response from AI")

                logger.success(f"[TRANSCRIPTION UTILS] [PROFILE] Generated successfully ({len(content)} chars).")
                return content.strip()

        except Exception as e:
            logger.warning(f"[TRANSCRIPTION UTILS] [PROFILE] Attempt {attempt} failed: {e}")
            
            if attempt == max_retries:
                logger.error(f"[TRANSCRIPTION UTILS] [PROFILE] All {max_retries} attempts failed.")
                raise HTTPException(502, detail=f"Clinical Profile Generation Failed: {e}")
            
            # Wait briefly before retry
            await asyncio.sleep(1)

async def identify_speaker_roles(utterances: list) -> dict:
    """
    Identifies which speaker label (A or B) corresponds to the Therapist vs Client.
    Uses Model 3 (DeepSeek) via OpenRouter with 3 Retries.
    """
    import json # Importing here to ensure availability if not at top-level

    if not MODEL3_KEY:
        logger.error("[TRANSCRIPTION UTILS] [ROLE_ID] MODEL3_API_KEY is missing.")
        raise HTTPException(500, detail="Server Configuration Error: MODEL3_API_KEY missing.")

    # 1. Prepare the dialogue sample (First 20 turns)
    lines = []
    for u in utterances:
        spk = u.get("speaker", "Unknown")
        txt = u.get("text", "")
        lines.append(f"Speaker {spk}: {txt}")
    
    sample_text = "\n".join(lines)
    
    # 2. Prepare Payload
    try:
        final_prompt = SPEAKER_IDENTIFICATION_PROMPT.format(transcript_sample=sample_text)
    except NameError:
         # Safety check if you forgot the import
        logger.error("[TRANSCRIPTION UTILS] [ROLE_ID] SPEAKER_IDENTIFICATION_PROMPT not imported.")
        raise HTTPException(500, detail="Server Error: Prompt template missing.")

    headers = {
        "Authorization": f"Bearer {MODEL3_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
    }
    
    payload = {
        "model": MODEL3_NAME,
        "messages": [
            {"role": "user", "content": final_prompt}
        ],
        "temperature": 0.1 
    }

    max_retries = MAX_RETRIES
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"[TRANSCRIPTION UTILS] [ROLE_ID] Identifying speakers (Attempt {attempt}/{max_retries})...")
            
            async with httpx.AsyncClient(trust_env=False) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                
                if resp.status_code != 200:
                    logger.warning(f"[TRANSCRIPTION UTILS] [ROLE_ID] Upstream Error: {resp.text}")
                    raise Exception(f"HTTP {resp.status_code}")

                content = resp.json()["choices"][0]["message"]["content"]

                # 4. Robust JSON Parsing (Handles Markdown blocks & <think> tags)
                # First, try to find a code block: ```json ... ```
                json_match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
                if json_match:
                    clean_json = json_match.group(1)
                else:
                    # Fallback: Find the first outer curly braces
                    json_match = re.search(r"\{.*\}", content, re.DOTALL)
                    if json_match:
                        clean_json = json_match.group(0)
                    else:
                        raise Exception("AI response did not contain valid JSON.")

                data = json.loads(clean_json)
                
                # 5. Invert Map for the Cleaning Function
                # LLM returns: {"Therapist": "Speaker A"}
                # We need: {"A": "Therapist"}
                final_map = {}
                
                # Clean the values (remove "Speaker " prefix if LLM included it)
                val_therapist = data.get("Therapist", "").replace("Speaker ", "").strip()
                val_client = data.get("Client", "").replace("Speaker ", "").strip()
                
                if val_therapist: final_map[val_therapist] = "Therapist"
                if val_client: final_map[val_client] = "Client"
                
                logger.success(f"[TRANSCRIPTION UTILS] [ROLE_ID] Successfully mapped: {final_map}")
                return final_map

        except Exception as e:
            logger.warning(f"[TRANSCRIPTION UTILS] [ROLE_ID] Attempt {attempt} failed: {e}")
            
            if attempt == max_retries:
                logger.error(f"[TRANSCRIPTION UTILS] [ROLE_ID] All {max_retries} attempts failed.")
                raise HTTPException(502, detail=f"Speaker Role Identification Failed after {max_retries} retries. Error: {e}")
            
            await asyncio.sleep(1)

async def impute_speaker_labels(cleaned_data: dict, role_map: dict) -> dict:
    """
    Replaces generic speaker labels (e.g., 'A', 'B') in the cleaned transcript
    with specific roles (e.g., 'Therapist', 'Client') using the provided map.
    """
    try:
        # 1. Validation: Ensure inputs are correct types
        if not isinstance(cleaned_data, dict) or "utterances" not in cleaned_data:
            logger.error(f"[IMPUTE] Invalid cleaned_data format. Expected dict with 'utterances' key.")
            raise HTTPException(
                status_code=422, 
                detail="Invalid input: 'cleaned_data' must be a dictionary containing an 'utterances' list."
            )
        
        if not isinstance(role_map, dict) or not role_map:
            logger.warning("[IMPUTE] Role map is empty or invalid. Skipping imputation.")
            return cleaned_data

        logger.info(f"[IMPUTE] Applying role map: {role_map}")

        # 2. Imputation Logic
        # We process a Deep Copy to avoid mutating the original object if something fails halfway
        updated_utterances = []
        
        for i, utterance in enumerate(cleaned_data["utterances"]):
            # Check for malformed utterance objects
            if not isinstance(utterance, dict) or "speaker" not in utterance:
                logger.warning(f"[IMPUTE] Skipping malformed utterance at index {i}")
                updated_utterances.append(utterance)
                continue
            
            original_speaker = utterance["speaker"]
            
            # Replace if the speaker exists in our map, otherwise keep original
            new_speaker = role_map.get(original_speaker, original_speaker)
            
            # Create new utterance object with updated speaker
            new_utterance = utterance.copy()
            new_utterance["speaker"] = new_speaker
            updated_utterances.append(new_utterance)

        # 3. Construct Result
        result = cleaned_data.copy()
        result["utterances"] = updated_utterances
        
        logger.success(f"[IMPUTE] Successfully updated {len(updated_utterances)} utterances.")
        return result

    except HTTPException as he:
        # Re-raise HTTP exceptions so they pass through to the client
        raise he
    except Exception as e:
        # Catch generic python errors and convert to 500
        logger.error(f"[IMPUTE] Critical Failure: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Internal Server Error during speaker imputation: {str(e)}"
        )