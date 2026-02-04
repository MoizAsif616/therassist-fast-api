# app/api/v1/transcription_routes.py

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from loguru import logger
from app.services.auth_service import authenticate
from app.services.db_service import check_session_ownership
from app.services.transcription_service import transcribe_session
from app.services.user_service import client_exists


router = APIRouter()

class TranscriptionRequest(BaseModel):
    client_id: str

class TranscriptionResponse(BaseModel):
    detail: str

@router.post("/transcribe/{session_id}", response_model=TranscriptionResponse)
async def run_transcription(
    session_id: str,
    payload: TranscriptionRequest,
    therapist_id: str = Depends(authenticate)
):
    client_exists(payload.client_id, therapist_id)

    check_session_ownership(session_id, payload.client_id, therapist_id)

    logger.info(f"[TRANSCRIPTION] Starting session {session_id} for T:{therapist_id}, C:{payload.client_id}")

    result = await transcribe_session(session_id)

    return TranscriptionResponse(
        detail="Transcription completed and further processing started."
    )