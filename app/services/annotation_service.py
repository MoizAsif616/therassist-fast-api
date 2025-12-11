import asyncio
import json
import os
import numpy as np
from huggingface_hub import InferenceClient
from loguru import logger
from fastapi import HTTPException
from app.services.db_service import get_session, update_processing_state
from app.core.supabase_client import db

# --- Configuration ---
HF_TOKEN = os.getenv("HF_TOKEN")
HF_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
THEMES_PATH = os.path.join(os.getcwd(), 'app', 'utils', 'themes_embeddings.json')

# --- Load Themes (Cached as NumPy Arrays) ---
THEMES_EMBEDDINGS = {}
try:
    with open(THEMES_PATH, 'r') as f:
        raw_themes = json.load(f)
        # Pre-convert to NumPy for fast math
        for k, v in raw_themes.items():
            THEMES_EMBEDDINGS[k] = np.array(v, dtype=np.float32)
    logger.info(f"Loaded {len(THEMES_EMBEDDINGS)} clinical themes.")
except FileNotFoundError:
    logger.warning(f"themes_embeddings.json not found. Theme analysis will skip.")

async def annotation_service(session_id: str):
    # 1. Validate State
    session = get_session(session_id)
    if session["processing_state"] != "TRANSCRIBED":
        raise HTTPException(400, f"Invalid state: {session['processing_state']}")

    logger.info(f"[ANNOTATION] Starting annotation for {session_id}")
    # update_processing_state(session_id, "ANNOTATING")

    # 2. Fetch Utterances
    try:
        resp = db()("utterances").select("*").eq("session_id", session_id).execute()
        utterances = resp.data
    except Exception as e:
        logger.error(f"DB Error: {e}")
        raise HTTPException(500, "Database fetch failed")

    if not utterances:
        # update_processing_state(session_id, "COMPLETED")
        return {"status": "skipped", "reason": "no_utterances"}

    # 3. Setup Client (Matches test.py)
    client = InferenceClient(model=HF_MODEL, token=HF_TOKEN)
    updates_payload = []

    # 4. Process One by One (Simple & Robust)
    for i, u in enumerate(utterances):
        text = u['utterance']
        if i % 5 == 0: logger.info(f"[ANNOTATION] Processing {i+1}/{len(utterances)}")

        try:
            # Run Sync call in a thread to keep server responsive
            # This handles URL routing/redirects automatically
            response = await asyncio.to_thread(client.feature_extraction, text)
            
            # Convert to NumPy (Handles List or Array output)
            vec = np.array(response)
            
            # Handle Dimensions (Fixes [[...]] nesting)
            if vec.ndim > 1: vec = vec[0]
            if vec.ndim > 1: vec = vec[0] # Double check
            
            # Normalize
            norm = np.linalg.norm(vec)
            if norm > 0: vec = vec / norm
            
            # Match Themes
            matched_themes = {}
            for theme_name, theme_vec in THEMES_EMBEDDINGS.items():
                score = np.dot(vec, theme_vec)
                if score >= 0.35:
                    matched_themes[theme_name] = round(float(score), 4)

            # Clean RAM
            del vec
            
            # Store result
            u['clinical_themes'] = matched_themes
            updates_payload.append(u)

        except Exception as e:
            logger.error(f"Skipping utterance {u['id']}: {e}")
            continue

    # 5. Bulk Save
    if updates_payload:
        logger.info(f"[ANNOTATION] Saving {len(updates_payload)} annotations...")
        db()("utterances").upsert(updates_payload).execute()

    update_processing_state(session_id, "ANNOTATED")
    return {"status": "Annotation completed.", "session_id": session_id}