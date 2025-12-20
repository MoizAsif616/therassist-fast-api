
from loguru import logger
from app.core.supabase_client import db

SESSIONS_TABLE = "sessions"

def _get_next_session_number(client_id: str, therapist_id: str) -> int:
    """
    Internal helper to calculate session sequence.
    """
    try:
        resp = db()(SESSIONS_TABLE) \
            .select("session_number") \
            .eq("client_id", client_id) \
            .eq("therapist_id", therapist_id) \
            .order("session_number", desc=True) \
            .limit(1) \
            .execute()
        
        if resp.data and resp.data[0].get("session_number") is not None:
            return resp.data[0]["session_number"] + 1
        return 1
    except Exception as e:
        logger.error(f"[DB UTILS:AUDIO UPLOAD] Failed to get session number: {e}")
        return 1

