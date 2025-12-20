import uuid
from datetime import datetime
from loguru import logger
from fastapi import HTTPException
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

def create_session_transaction(
    client_id: str,
    therapist_id: str,
    duration_hms: str,
    audio_hash: str,
    audio_url: str
) -> str:
    """
    Performs the database insertion as a single atomic unit.
    """
    session_number = _get_next_session_number(client_id, therapist_id)

    payload = {
        "client_id": client_id,
        "therapist_id": therapist_id,
        "session_number": session_number,
        "audio_url": audio_url,             # Audio is already uploaded
        "processing_state": "UPLOADED",
        "duration_hms": duration_hms,
        "audio_hash": audio_hash,
        "chunks_path": None,
        "created_at": datetime.utcnow().isoformat(),
    }

    logger.info(f"[DB UTILS:AUDIO UPLOAD] Inserting Session (Seq: {session_number})")

    try:
        # FIX: Remove .select() and .single()
        # PostgREST returns the inserted row(s) automatically.
        response = db()(SESSIONS_TABLE).insert(payload).execute()
        
        # The data is returned as a list of dicts: [{'id': '...', ...}]
        if response.data and len(response.data) > 0:
            new_session_id = response.data[0]['id']
            return new_session_id
        else:
            return "Session created, but no ID returned."
    except Exception as e:
        logger.error(f"[DB UTILS:AUDIO UPLOAD] Insert Failed: {e}")
        # Raising this 500 triggers the `except` block in the Service layer
        # which will then delete the file from R2.
        raise HTTPException(status_code=500, detail=f"[DB UTILS:AUDIO UPLOAD] Database Commit Failed: {e}")