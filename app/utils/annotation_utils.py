from collections import Counter
from loguru import logger
from fastapi import HTTPException
from app.core.supabase_client import db

def get_client_id_from_session(session_id: str) -> str:
    """Fetches client_id associated with a session."""
    try:
        resp = db()("sessions")\
            .select("client_id")\
            .eq("id", session_id)\
            .single()\
            .execute()
        return resp.data["client_id"]
    except Exception as e:
        logger.error(f"[ANNOTATION UTILS] Failed to get client_id: {e}")
        # We raise error because we cannot proceed without a client ID for insights
        raise HTTPException(500, detail="Could not find client for this session.")

def get_client_emotion_map(client_id: str) -> dict:
    """Fetches existing emotion map from client_insights. Returns empty dict if none."""
    try:
        resp = db()("client_insights")\
            .select("emotion_map")\
            .eq("client_id", client_id)\
            .maybe_single()\
            .execute()
        
        if resp and resp.data and resp.data.get("emotion_map"):
            logger.info(f"[ANNOTATION UTILS] Fetched existing emotion map for client {client_id}")
            return resp.data["emotion_map"]
        logger.info(f"[ANNOTATION UTILS] No existing emotion map for client {client_id}")
        return {}
    except Exception as e:
        logger.error(f"[ANNOTATION UTILS] Failed to fetch client insights: {e}")
        raise HTTPException(500, detail="Could not fetch client insights.")

def compute_emotion_maps(utterances: list[dict], existing_client_map: dict) -> tuple[dict, dict]:
    """
    Computes:
    1. Session Map: Count of emotions in THIS session.
    2. Client Map: Merged count of (Old Client Map + Session Map).
    """

    logger.info(f"[ANNOTATION UTILS] Computing emotion maps.")
    session_counter = Counter()

    # 1. Tally this session
    for u in utterances:
        themes = u.get("clinical_themes", {})
        if themes:
            # 'themes' is a dict { "Anxiety": 0.85, ... }
            # We count the KEYS (presence of emotion), not the scores
            for theme_name in themes.keys():
                session_counter[theme_name] += 1
    
    session_map = dict(session_counter)

    # 2. Merge with Client History
    client_counter = Counter(existing_client_map)
    client_counter.update(session_counter)
    
    client_map = dict(client_counter)
    logger.success(f"[ANNOTATION UTILS] Computed emotion maps.")
    return session_map, client_map