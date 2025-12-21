import asyncio
import json
import os
import numpy as np
from huggingface_hub import InferenceClient
from loguru import logger
from fastapi import HTTPException
from app.services.db_service import get_session
from app.core.supabase_client import get_supabase_client

# Import new utils
from app.utils.annotation_utils import (
    get_client_id_from_session,
    get_client_emotion_map,
    compute_emotion_maps
)
from app.utils.transaction_utils import commit_annotation_transaction

# --- Configuration ---
HF_TOKEN = os.getenv("HF_TOKEN")
HF_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
THEMES_PATH = os.path.join(os.getcwd(), 'app', 'utils', 'themes_embeddings.json')

# --- Load Themes ---
THEMES_EMBEDDINGS = {}
try:
    with open(THEMES_PATH, 'r') as f:
        raw_themes = json.load(f)
        for k, v in raw_themes.items():
            THEMES_EMBEDDINGS[k] = np.array(v, dtype=np.float32)
    logger.info(f"Loaded {len(THEMES_EMBEDDINGS)} clinical themes.")
except FileNotFoundError:
    logger.warning(f"themes_embeddings.json not found.")

async def annotation_service(session_id: str):
    # 1. Validate State
    session = get_session(session_id)
    if session["processing_state"] != "TRANSCRIBED":
        logger.warning(f"Skipping annotation. State is {session['processing_state']}")
        raise HTTPException(400, detail="Session not ready for annotation or it has already been annotated.")
        
        
    logger.info(f"[ANNOTATION] Starting annotation for {session_id}")

    # 2. Fetch Utterances
    try:
        resp = get_supabase_client().from_("utterances").select("*").eq("session_id", session_id).execute()
        utterances = resp.data
    except Exception as e:
        logger.error(f"DB Error: {e}")
        raise HTTPException(500, detail="Database fetch failed")

    if not utterances:
        logger.warning(f"No utterances found for session {session_id}")
        raise HTTPException(404, detail="No utterances found for this session.")

    # 3. Setup Client
    client = InferenceClient(model=HF_MODEL, token=HF_TOKEN)
    annotated_utterances = []

    # 4. Process Embeddings (Existing Logic)
    for i, u in enumerate(utterances):
        text = u['utterance']
        if i % 10 == 0: logger.info(f"[ANNOTATION] Processing {i+1}/{len(utterances)}")

        try:
            # Run Sync call in thread
            response = await asyncio.to_thread(client.feature_extraction, text)
            vec = np.array(response)
            if vec.ndim > 1: vec = vec[0]
            if vec.ndim > 1: vec = vec[0]
            
            norm = np.linalg.norm(vec)
            if norm > 0: vec = vec / norm
            
            matched_themes = {}
            for theme_name, theme_vec in THEMES_EMBEDDINGS.items():
                score = np.dot(vec, theme_vec)
                if score >= 0.35:
                    matched_themes[theme_name] = round(float(score), 4)

            u['clinical_themes'] = matched_themes
            annotated_utterances.append(u)

        except Exception as e:
            logger.warning(f"[ANNOTATION] Failed to annotate utterance {u['id']}: {e}")
            raise HTTPException(500, detail="Annotation processing failed.")

    # 5. NEW: Compute Maps
    logger.info(f"[ANNOTATION] Computing Emotion Maps...")
    
    # A. Get IDs
    client_id = get_client_id_from_session(session_id)
    
    # B. Get Old Client History
    existing_client_map = get_client_emotion_map(client_id)
    
    # C. Calculate New Maps
    session_map, updated_client_map = compute_emotion_maps(annotated_utterances, existing_client_map)

    # logger.info(f"[ANNOTATION - Moiz] Intentionally failing for debugging purposes.")
    # raise HTTPException(500, detail="Annotation failed.")

    # 6. NEW: Transaction Commit
    logger.info(f"[ANNOTATION] Committing Transaction...")
    commit_annotation_transaction(
        session_id=session_id,
        client_id=client_id,
        utterances=annotated_utterances,
        session_emotions=session_map,
        client_emotions=updated_client_map
    )

    return {"detail": "Annotation completed.", "session_id": session_id}