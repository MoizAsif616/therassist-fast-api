
from http.client import HTTPException
from loguru import logger
from typing import Optional
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
        raise HTTPException(500, detail="Failed to get next session number.")
    
async def get_session_number(session_id: str) -> Optional[int]:
    """
    Fetches the integer session_number (e.g., 4) from the UUID session_id.
    Returns None if not found.
    """
    try:
        logger.info(f"[DB SERVICE] Fetching session number for session_id: {session_id}")
        response = db()("sessions")\
            .select("session_number")\
            .eq("id", session_id)\
            .maybe_single()\
            .execute()
        
        if response.data:
            return response.data["session_number"]
        else:
            logger.error(f"[DB SERVICE] Session number not found for {session_id}")
            raise HTTPException(404, detail="Failed to get session number.")

    except Exception as e:
        logger.error(f"[DB SERVICE] Failed to get session number for {session_id}: {e}")
        raise HTTPException(500, detail="Failed to get session number.")

