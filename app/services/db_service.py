# app/services/db_service.py

from datetime import datetime
import uuid

from fastapi import HTTPException
from loguru import logger
from app.core.supabase_client import db


SESSIONS_TABLE = "sessions"
CLIENTS_TABLE = "clients"
THERAPISTS_TABLE = "therapists"


def client_exists(client_id: str) -> bool:
    """
    Checks if a client exists in the 'clients' table.
    Returns True/False.

    Raises HTTPException only if Supabase query fails.
    """

    logger.info(f"[CLIENT] Checking client {client_id}")

    try:
        resp = db()(CLIENTS_TABLE).select("id").eq("id", client_id).maybe_single().execute()
    except Exception as e:
        raise HTTPException(500, f"Failed to query client: {e}")

    if not resp or not resp.data:
        logger.warning(f"[CLIENT] Client {client_id} not found.")
        return False

    logger.info(f"[CLIENT] Client {client_id} exists.")
    return True



def therapist_exists(therapist_id: str) -> bool:
    """
    Checks if a therapist exists in the 'therapists' table.
    Returns True/False.

    Raises HTTPException only if Supabase query fails.
    """

    logger.info(f"[THERAPIST] Checking therapist {therapist_id}")

    try:
        resp = db()(THERAPISTS_TABLE).select("id").eq("id", therapist_id).maybe_single().execute()
    except Exception as e:
        raise HTTPException(500, f"Failed to query therapist: {e}")

    if not resp or not resp.data:
        logger.warning(f"[THERAPIST] Therapist {therapist_id} not found.")
        return False

    logger.info(f"[THERAPIST] Therapist {therapist_id} exists.")
    return True


# --------------------------
# Create a new session
# --------------------------

def create_session(
    client_id: str,
    therapist_id: str,
    duration_hms: str,
    audio_hash: str
) -> str:
    session_id = str(uuid.uuid4())
    session_number = get_next_session_number(client_id, therapist_id)


    payload = {
        "id": session_id,
        "client_id": client_id,
        "therapist_id": therapist_id,
        "audio_url": None,
        "chunks_path": None,
        "processing_state": "UPLOADED",
        "duration_hms": duration_hms,
        "created_at": datetime.utcnow().isoformat(),
        "audio_hash": audio_hash,
        "session_number": session_number

    }

    logger.info(f"[DB] Creating session {session_id}")

    try:
        db()(SESSIONS_TABLE).insert(payload).execute()
    except Exception as e:
        logger.error(f"[DB] Insert error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create session: {e}")

    return session_id


# --------------------------
# Update audio URL after upload
# --------------------------

def update_session_audio_path(session_id: str, audio_path: str):
    try:
        db()(SESSIONS_TABLE).update({
            "audio_url": audio_path,
        }).eq("id", session_id).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update audio path: {e}")


# --------------------------
# Update processing state
# --------------------------

def update_processing_state(session_id: str, state: str):
    try:
        db()(SESSIONS_TABLE).update({
            "processing_state": state,
        }).eq("id", session_id).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update processing state: {e}")


# --------------------------
# Fetch session
# --------------------------

def get_session(session_id: str) -> dict:
    try:
        resp = db()(SESSIONS_TABLE).select("*").eq("id", session_id).maybe_single().execute()
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Session not found.")

    if not resp.data:
        raise HTTPException(status_code=404, detail="Session not found.")

    return resp.data


def session_with_same_audio_exists(client_id: str, therapist_id: str, audio_hash: str) -> bool:
    try:
        resp = db()("sessions") \
            .select("id") \
            .eq("client_id", client_id) \
            .eq("therapist_id", therapist_id) \
            .eq("audio_hash", audio_hash) \
            .execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    return len(resp.data) > 0

def get_next_session_number(client_id: str, therapist_id: str) -> int:
    """
    Returns the next session_number for this client–therapist pair.
    """
    try:
        resp = db()("sessions") \
            .select("session_number") \
            .eq("client_id", client_id) \
            .eq("therapist_id", therapist_id) \
            .order("session_number", desc=True) \
            .limit(1) \
            .execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    if resp.data and resp.data[0].get("session_number") is not None:
        return resp.data[0]["session_number"] + 1

    return 1


def store_utterances(session_id: str, utterances: list[dict]):
    """
    Insert cleaned utterances into the utterances table.
    Each item in utterances must contain:
        - speaker
        - start_time
        - end_time
        - text  (utterance text)
    clinical_themes is NULL for now.
    """
    rows = []
    for u in utterances:
        rows.append({
            "session_id": session_id,
            "speaker": u.get("speaker"),
            "start_time": u.get("start_time"),
            "end_time": u.get("end_time"),
            "utterance": u.get("text"),
            "clinical_themes": None
        })

    try:
        db()("utterances").insert(rows).execute()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to store utterances: {e}"
        )

def update_session_summary(session_id: str, summary: str):
    """
    Update the session summary field in the sessions table.
    """
    try:
        db()("sessions").update({
            "summary": summary
        }).eq("id", session_id).execute()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update session summary: {e}"
        )

def update_session_sentiment(session_id: str, score: float):
    """
    Updates the sentiment_score for a session.
    """
    logger.info(f"[DB] Updating sentiment for session {session_id} to {score}")
    try:
        db()(SESSIONS_TABLE).update({
            "sentiment_score": score
        }).eq("id", session_id).execute()
    except Exception as e:
        # We log error but usually don't crash the whole flow for a metric update
        logger.error(f"[DB] Failed to update sentiment score: {e}")
        # Only raise if you want the endpoint to return 500
        raise HTTPException(status_code=500, detail=f"Failed to update sentiment: {e}")
    
def update_session_theme(session_id: str, theme: str, explanation: str):
    """
    Updates the session with the identified clinical theme and explanation.
    """
    logger.info(f"[DB] Updating theme for session {session_id}: {theme}")
    try:
        db()(SESSIONS_TABLE).update({
            "theme": theme,
            "theme_explanation": explanation
        }).eq("id", session_id).execute()
    except Exception as e:
        # Log error but don't crash the pipeline
        logger.error(f"[DB] Failed to update theme: {e}")
        raise
    
# app/services/db_service.py

# ... (Existing imports and functions) ...

def update_speaker_stats(session_id: str, therapist_time: float, therapist_count: int, client_time: float, client_count: int):
    """
    Updates the session with speaker statistics (time and utterance counts).
    Time is stored in seconds (float).
    """
    logger.info(f"[DB] Updating speaker stats for session {session_id}")
    try:
        db()(SESSIONS_TABLE).update({
            "therapist_time": therapist_time,
            "therapist_count": therapist_count,
            "client_time": client_time,
            "client_count": client_count
        }).eq("id", session_id).execute()
    except Exception as e:
        logger.error(f"[DB] Failed to update speaker stats: {e}")