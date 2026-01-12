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

    logger.info(f"[TRANSACTION UTILS : AUDIO UPLOAD] Inserting Session (Seq: {session_number})")

    try:
        # FIX: Remove .select() and .single()
        # PostgREST returns the inserted row(s) automatically.
        response = db()(SESSIONS_TABLE).insert(payload).execute()
        
        # The data is returned as a list of dicts: [{'id': '...', ...}]
        if response.data and len(response.data) > 0:
            new_session_id = response.data[0]['id']
            logger.success(f"[TRANSACTION : AUDIO UPLOAD] Inserted Session ID: {new_session_id}")
            return new_session_id
        else:
            return "Session created, but no ID returned."
    except Exception as e:
        logger.error(f"[TRANSACTION : AUDIO UPLOAD] Insert Failed: {e}")
        # Raising this 500 triggers the `except` block in the Service layer
        # which will then delete the file from R2.
        raise HTTPException(status_code=500, detail=f"Database Commit Failed: {e}")

def commit_transcription_transaction(
    session_id: str,
    client_id: str,         # <--- NEW ARGUMENT
    summary: str,
    sentiment_score: float,
    theme: str,
    explanation: str,
    utterances: list[dict],
    stats: dict,
    client_profile: str     # <--- NEW ARGUMENT
):
    logger.info(f"[TRANSCRIPTION TRANSACTION] RPC Commit for {session_id}")

    try:
        # Calls your superior SQL function
        get_supabase_client().rpc("commit_transcription", {
            "p_session_id": session_id,
            "p_client_id": client_id,            # <--- PASS THIS
            "p_summary": summary,
            "p_sentiment": sentiment_score,
            "p_theme": theme,
            "p_theme_explanation": explanation,
            "p_stats": stats,
            "p_utterances": utterances,
            "p_client_profile": client_profile   # <--- PASS THIS
        }).execute()
        
        logger.success(f"[TRANSCRIPTION TRANSACTION] Success for {session_id}")

    except Exception as e:
        logger.error(f"[TRANSCRIPTION TRANSACTION] RPC Failed: {e}")
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
        
        logger.success(f"[ANNOTATION TRANSACTION] Success for {session_id}")

    except Exception as e:
        logger.error(f"[ANNOTATION TRANSACTION] RPC Failed: {e}")
        raise HTTPException(500, detail=f"Annotation Database Transaction Failed: {e}")


def commit_embedding_transaction(
    session_id: str,
    summary_embedding: list[float],
    utterances: list[dict]
):
    """
    Commits the RAG embeddings to the database via RPC.
    
    Args:
        session_id: UUID of the session.
        summary_embedding: List of floats (1536 dim).
        utterances: List of dicts. Each dict MUST look like: {"id": "uuid", "embedding": [0.1, ...]}
    """
    logger.info(f"[EMBEDDING TRANSACTION] RPC Commit for {session_id}")
    
    try:
        # We send the utterances as a list of dicts. 
        # Supabase/Postgres will handle the conversion to JSONB automatically.
        response = get_supabase_client().rpc("commit_embedding", {
            "p_session_id": session_id,
            "p_summary_embedding": summary_embedding,
            "p_utterances": utterances
        }).execute()
        
        logger.success(f"[EMBEDDING TRANSACTION] Success. Session {session_id} marked as EMBEDDED.")
        return response

    except Exception as e:
        logger.error(f"[EMBEDDING TRANSACTION] RPC Failed: {e}")
        # We raise 500 because if this fails, we have a data consistency issue
        raise HTTPException(500, detail=f"Embedding Database Transaction Failed: {e}")