# app/services/transcription_service.py

import os
import asyncio
import tempfile
import httpx
from fastapi import HTTPException
from loguru import logger
import asyncio
import re


from app.core.supabase_client import storage, db
from app.services.annotation_service import annotation_service
from app.services.db_service import (
    get_session,
    update_processing_state,
    update_session_summary,
    store_utterances,
    update_session_sentiment,
    update_session_theme,
    update_speaker_stats
)
from app.utils.promt_templates import SESSION_SUMMARY_PROMPT, SENTIMENT_ANALYSIS_PROMPT, THEME_EXTRACTION_PROMPT

ASSEMBLY_KEY = os.getenv("ASSEMBLYAI_API_KEY")
UPLOAD_URL = "https://api.assemblyai.com/v2/upload"
TRANSCRIPT_URL = "https://api.assemblyai.com/v2/transcript"

NOVA_API_KEY = os.getenv("NOVA_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "amazon/nova-2-lite-v1:free")

# --------------------------------------------------------------
# Helpers
# --------------------------------------------------------------

async def _download_from_supabase(storage_path: str, dst_path: str):
    try:
        bucket = storage.from_("therapy-sessions")
        data = bucket.download(storage_path)
    except Exception as e:
        raise HTTPException(500, detail = f"Failed to download audio: {e}")

    content = data["content"] if isinstance(data, dict) else data
    with open(dst_path, "wb") as f:
        f.write(content)


async def _upload_to_assembly(file_path: str) -> str:
    if not ASSEMBLY_KEY:
        raise HTTPException(500, detail = "ASSEMBLYAI_API_KEY missing")

    headers = {"authorization": ASSEMBLY_KEY}

    async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=30)) as client:
        with open(file_path, "rb") as f:
            file_bytes = f.read()
        resp = await client.post(
            UPLOAD_URL,
            headers=headers,
            content=file_bytes
        )
        resp.raise_for_status()

    return resp.json()["upload_url"]



async def _create_transcription(upload_url: str) -> str:
    headers = {"authorization": ASSEMBLY_KEY, "content-type": "application/json"}
    payload = {
        "audio_url": upload_url,
        "speaker_labels": True,
        "speakers_expected": 2,
        "punctuate": True,
        "format_text": True,
        "language_code": "en",
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=30)) as client:
        resp = await client.post(TRANSCRIPT_URL, headers=headers, json=payload)
        resp.raise_for_status()

    return resp.json()["id"]


async def _poll_transcription(tid: str) -> dict:
    headers = {"authorization": ASSEMBLY_KEY}
    url = f"{TRANSCRIPT_URL}/{tid}"

    async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=30)) as client:
        while True:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()

            j = resp.json()
            if j["status"] == "completed":
                return j
            if j["status"] == "error":
                raise HTTPException(502, detail = f"AssemblyAI error: {j.get('error')}")

            await asyncio.sleep(3)


def ms_to_hms(ms: int) -> str:
    s = ms // 1000
    return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"


def clean_transcription_result(raw_json: dict) -> dict:
    cleaned = {"text": raw_json.get("text", ""), "utterances": []}
    for u in raw_json.get("utterances", []):
        cleaned["utterances"].append({
            "speaker": u.get("speaker"),
            "start_time": ms_to_hms(u.get("start", 0)),
            "end_time": ms_to_hms(u.get("end", 0)),
            "text": u.get("text", "")
        })
    return cleaned


async def _generate_summary(session_id: str, text: str) -> str:
    if not NOVA_API_KEY:
        raise HTTPException(500, detail = "NOVA_API_KEY missing")

    headers = {
        "Authorization": f"Bearer {NOVA_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "Therassist API"
    }

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "You summarize therapy sessions professionally."},
            {"role": "user", "content": SESSION_SUMMARY_PROMPT.format(transcription_text=text)},
        ]
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=120
        )
        resp.raise_for_status()

    summary = resp.json()["choices"][0]["message"]["content"]
    update_session_summary(session_id, summary)
    return summary

async def _generate_sentiment(session_id: str, text: str) -> float:
    """
    Calls LLM to analyze client sentiment and extracts a float score (-1.0 to 1.0).
    Updates the session record in the DB with the score.
    """
    if not NOVA_API_KEY:
        logger.warning("NOVA_API_KEY missing, skipping sentiment analysis.")
        return 0.0

    headers = {
        "Authorization": f"Bearer {NOVA_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "Therassist API"
    }

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "You are a clinical sentiment analyzer."},
            {"role": "user", "content": SENTIMENT_ANALYSIS_PROMPT.format(transcription_text=text)},
        ],
        "temperature": 0.1, # Low temp for consistent scoring
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=30 # Short timeout for sentiment
            )
            resp.raise_for_status()
            
        content = resp.json()["choices"][0]["message"]["content"]
        
        # reliable regex to find the score at the end
        # Looks for: SENTIMENT_SCORE: followed by optional whitespace and a float
        match = re.search(r"SENTIMENT_SCORE:\s*([-+]?\d*\.\d+|\d+)", content)
        
        if match:
            score = float(match.group(1))
            # Clamp value just in case
            score = max(-1.0, min(1.0, score))
        else:
            logger.warning(f"Could not parse sentiment score from: {content[:50]}...")
            score = 0.0 # Default/Neutral on failure
        return score

    except Exception as e:
        logger.error(f"Sentiment analysis failed: {e}")
        return 0.0
    
async def _generate_theme(session_id: str, text: str) -> dict:
    """
    Calls LLM to identify the clinical theme and explanation.
    """
    if not NOVA_API_KEY:
        return {"theme": None, "explanation": None}

    headers = {
        "Authorization": f"Bearer {NOVA_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "Therassist API"
    }

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "You are a clinical classification assistant."},
            # This will now use the NEW comprehensive prompt
            {"role": "user", "content": THEME_EXTRACTION_PROMPT.format(transcription_text=text)},
        ],
        "temperature": 0.1, 
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=30 
            )
            resp.raise_for_status()
            
        content = resp.json()["choices"][0]["message"]["content"]
        
        # Regex to extract the lines
        theme_match = re.search(r"THEME:\s*(.+)", content)
        explanation_match = re.search(r"EXPLANATION:\s*(.+)", content)
        
        theme = theme_match.group(1).strip() if theme_match else "General Consultation"
        explanation = explanation_match.group(1).strip() if explanation_match else "Analysis failed to extract specific explanation."

        return {"theme": theme, "explanation": explanation}

    except Exception as e:
        logger.error(f"Theme extraction failed: {e}")
        return {"theme": "Error", "explanation": str(e)}


# --------------------------------------------------------------
# MAIN FUNCTION (async, unified for both route & background)
# --------------------------------------------------------------

async def transcribe_session(session_id: str, local_file_path: str | None = None):
    session = get_session(session_id)

    if session["processing_state"] != "UPLOADED":
        raise HTTPException(400, detail = f"Transcription allowed only in UPLOADED state, got {session['processing_state']}")

    # Determine file location
    if local_file_path:
        file_path = local_file_path
    else:
        audio_url = session["audio_url"]
        if not audio_url:
            raise HTTPException(400, detail = "No audio_url in session")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".audio") as tmp:
            file_path = tmp.name

        await _download_from_supabase(audio_url, file_path)

    try:
        logger.info(f"[TRANSCRIPTION] Uploading session {session_id} to AssemblyAI")
        upload_url = await _upload_to_assembly(file_path)

        logger.info(f"[TRANSCRIPTION] Creating transcription for session {session_id}")
        tid = await _create_transcription(upload_url)
        raw = await _poll_transcription(tid)

        logger.info(f"[TRANSCRIPTION] Completed transcription for session {session_id}")
        cleaned = clean_transcription_result(raw)

        logger.info(f"[TRANSCRIPTION] Calculating speaker stats for session {session_id}")
        therapist_time_ms = 0
        therapist_count = 0
        client_time_ms = 0
        client_count = 0

        # Iterate through RAW utterances to get precise ms values
        for u in raw.get("utterances", []):
            speaker = u.get("speaker") # 'A', 'B', etc.
            duration = u.get("end") - u.get("start")
            
            if speaker == 'A':
                therapist_count += 1
                therapist_time_ms += duration
            elif speaker == 'B':
                client_count += 1
                client_time_ms += duration
        
        # Convert ms to seconds (float)
        therapist_time_sec = round(therapist_time_ms / 1000.0, 2)
        client_time_sec = round(client_time_ms / 1000.0, 2)

        # Update DB immediately
        update_speaker_stats(session_id, therapist_time_sec, therapist_count, client_time_sec, client_count)

        logger.info(f"[TRANSCRIPTION] Generating AI Insights (Summary, Sentiment, Theme) for {session_id}")
        full_text = cleaned["text"]

        # 1. Create tasks (Don't await them yet)
        summary_task = _generate_summary(session_id, full_text)
        sentiment_task = _generate_sentiment(session_id, full_text)
        theme_task = _generate_theme(session_id, full_text)
        
        # 2. Run in parallel and wait for all to finish
        summary, sentiment_score, theme_data = await asyncio.gather(
            summary_task, 
            sentiment_task, 
            theme_task
        )
        logger.info(f"[TRANSCRIPTION] Storing theme with explanation for session {session_id}")
        update_session_theme(session_id, theme_data["theme"], theme_data["explanation"])

        logger.info(f"[TRANSCRIPTION] Storing utterances for session {session_id}")
        store_utterances(session_id, cleaned["utterances"])

        logger.info(f"[TRANSCRIPTION] Updating sentiment score for session {session_id}")
        update_session_sentiment(session_id, sentiment_score)

        logger.info(f"[TRANSCRIPTION] Updating processing state for session {session_id}")
        update_processing_state(session_id, "TRANSCRIBED")

        logger.info(f"[TRANSCRIPTION] Updating speaker stats for session {session_id}")
        update_speaker_stats(
            session_id,
            therapist_time_sec,
            therapist_count,
            client_time_sec,
            client_count
        )

        logger.info(f"[TRANSCRIPTION] Triggering annotation for session {session_id}")
        asyncio.create_task(annotation_service(session_id))

        return {
            "text": cleaned["text"],
            "summary": summary,
            "utterances": cleaned["utterances"],
            # "raw" : raw,
        }

    finally:
        # always delete local file
        if local_file_path and os.path.exists(local_file_path):
            try: os.remove(local_file_path)
            except: pass
