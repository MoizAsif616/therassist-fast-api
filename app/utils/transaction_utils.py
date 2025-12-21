from loguru import logger
from fastapi import HTTPException
from app.core.supabase_client import db
from datetime import datetime
from app.core.supabase_client import get_supabase_client
from app.utils.db_utils import _get_next_session_number


SESSIONS_TABLE = "sessions"
UTTERANCES_TABLE = "utterances"
client = get_supabase_client()


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

def commit_transcription_transaction(
    session_id: str,
    summary: str,
    sentiment_score: float,
    theme: str,
    explanation: str,
    utterances: list[dict],
    stats: dict
):
    logger.info(f"[TRANSCRIPTION TRANSACTION] RPC Commit for {session_id}")

    try:
        # Calls your superior SQL function
        client.rpc("commit_transcription", {
            "p_session_id": session_id,
            "p_summary": summary,
            "p_sentiment": sentiment_score,
            "p_theme": theme,
            "p_theme_explanation": explanation,
            "p_stats": stats,
            "p_utterances": utterances
        }).execute()
        
        logger.info(f"[TRANSCRIPTION TRANSACTION] Success for {session_id}")

    except Exception as e:
        logger.error(f"[TRANSCRIPTION TRANSACTION] RPC Failed: {e}")
        # Supabase returns specific error messages that are helpful for debugging
        raise HTTPException(500, detail=f"Database Transaction Failed: {e}")
    

def commit_annotation_transaction(
    session_id: str,
    client_id: str,
    utterances: list[dict],
    session_emotions: dict,
    client_emotions: dict
):
    logger.info(f"[ANNOTATION TRANSACTION] RPC Commit for {session_id}")
    
    try:
        get_supabase_client().rpc("commit_annotation", {
            "p_session_id": session_id,
            "p_client_id": client_id,
            "p_utterances": utterances,
            "p_session_emotions": session_emotions,
            "p_client_emotions": client_emotions
        }).execute()
        
        logger.info(f"[ANNOTATION TRANSACTION] Success for {session_id}")

    except Exception as e:
        logger.error(f"[ANNOTATION TRANSACTION] RPC Failed: {e}")
        raise HTTPException(500, detail=f"Annotation Database Transaction Failed: {e}")