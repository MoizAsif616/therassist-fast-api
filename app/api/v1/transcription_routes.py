# app/api/v1/transcription_routes.py

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from loguru import logger

from app.services.auth_service import authorize
from app.services.db_service import get_session, client_exists, therapist_exists
from app.services.transcription_service import transcribe_session


router = APIRouter()


# ----- Request Schema --------------------------------------------------------

class TranscriptionRequest(BaseModel):
    client_id: str
    therapist_id: str

class TranscriptionResponse(BaseModel):
    message: str
    # raw : dict
    # text: str
    # summary: str | None
    # utterances: list[dict]



# ----- Route ----------------------------------------------------------------

@router.post("/transcribe/{session_id}")
async def run_transcription(
    session_id: str,
    payload: TranscriptionRequest,
    authorization: str = Header(...)
):
    """
    SUBTASK 1:
    Validate -> ownership -> call transcription -> return raw AssemblyAI JSON
    """
    print("Checkign authorization:")
    # --- validate auth ------------------------------------------------------
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization.replace("Bearer ", "").strip()

    if not authorize(token):
        raise HTTPException(status_code=401, detail="Unauthorized")

    # --- validate client & therapist ---------------------------------------
    if not client_exists(payload.client_id):
        raise HTTPException(status_code=400, detail="Client does not exist")

    if not therapist_exists(payload.therapist_id):
        raise HTTPException(status_code=400, detail="Therapist does not exist")

    # --- fetch & validate session ownership --------------------------------
    session = get_session(session_id)

    if session["client_id"] != payload.client_id:
        raise HTTPException(status_code=403, detail="Session does not belong to this client")

    if session["therapist_id"] != payload.therapist_id:
        raise HTTPException(status_code=403, detail="Session does not belong to this therapist")

    # --- perform transcription ---------------------------------------------
    logger.info(f"[TRANSCRIPTION] Starting session {session_id}")

    result = await transcribe_session(session_id)

    return TranscriptionResponse(
        message="Transcription completed successfully.",
        # raw=result.get("raw", {}),
        # text=result.get("text", ""),
        # summary=result.get("summary"),
        # utterances=result.get("utterances", [])
    )
