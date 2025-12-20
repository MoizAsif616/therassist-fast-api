import os
import asyncio
import httpx
import re
import statistics
from fastapi import HTTPException
from loguru import logger
from app.utils.promt_templates import SESSION_SUMMARY_PROMPT, SENTIMENT_ANALYSIS_PROMPT, THEME_EXTRACTION_PROMPT

# --- MODEL CONFIGURATION ---
MODEL1_NAME = os.getenv("MODEL1_NAME")
MODEL1_KEY = os.getenv("MODEL1_API_KEY")

MODEL2_NAME = os.getenv("MODEL2_NAME")
MODEL2_KEY = os.getenv("MODEL2_API_KEY")

MODEL3_NAME = os.getenv("MODEL3_NAME")
MODEL3_KEY = os.getenv("MODEL3_API_KEY")

# --------------------------------------------------------------
# 1. SUMMARY GENERATION
# --------------------------------------------------------------
async def generate_summary(session_id: str, text: str) -> str:
    if not MODEL3_KEY:
        raise HTTPException(500, detail="Server misconfiguration: MODEL3_API_KEY missing.")

    headers = {
        "Authorization": f"Bearer {MODEL3_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
    }
    payload = {
        "model": MODEL3_NAME,
        "messages": [
            {"role": "system", "content": "You summarize therapy sessions professionally."},
            {"role": "user", "content": SESSION_SUMMARY_PROMPT.format(transcription_text=text)},
        ]
    }

    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            resp = await client.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers, timeout=120)
            if resp.status_code != 200:
                logger.error(f"[SUMMARY] Upstream Error: {resp.text}")
                raise HTTPException(502, detail=f"Summary Failed: {resp.status_code}")

        summary = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        if not summary: 
            raise HTTPException(502, detail="Summary AI returned empty response.")
        
        return summary

    except Exception as e:
        logger.error(f"[SUMMARY] Exception: {e}")
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
        async with httpx.AsyncClient(trust_env=False) as client:
            resp = await client.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers, timeout=45)
            if resp.status_code != 200:
                logger.error(f"[THEME] Upstream Error: {resp.text}")
                raise HTTPException(502, detail=f"Theme Failed: {resp.status_code}")
            
        content = resp.json()["choices"][0]["message"]["content"]
        theme_match = re.search(r"THEME:\s*(.+)", content)
        explanation_match = re.search(r"EXPLANATION:\s*(.+)", content)
        
        if not theme_match: 
            raise HTTPException(502, detail="AI response missing 'THEME:' tag.")
            
        return {
            "theme": theme_match.group(1).strip(),
            "explanation": explanation_match.group(1).strip() if explanation_match else "No explanation."
        }

    except Exception as e:
        logger.error(f"[THEME] Exception: {e}")
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
    tasks = [
        _fetch_single_sentiment(MODEL1_NAME, MODEL1_KEY, text),
        _fetch_single_sentiment(MODEL2_NAME, MODEL2_KEY, text),
        _fetch_single_sentiment(MODEL3_NAME, MODEL3_KEY, text)
    ]
    results = await asyncio.gather(*tasks)
    valid = [r for r in results if r is not None]
    
    if not valid:
        logger.error("CRITICAL: All 3 sentiment models failed.")
        raise HTTPException(502, detail="Sentiment Analysis Failed: All AI models returned errors.")

    return statistics.mean(valid)