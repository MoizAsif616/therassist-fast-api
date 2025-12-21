# app/api/v1/transcription_routes.py

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from loguru import logger

# Import the new dependency function
# Import the updated service functions
from app.services.auth_service import authenticate
from app.services.db_service import check_session_ownership
from app.services.transcription_service import transcribe_session
from app.services.user_service import client_exists


router = APIRouter()

# ----- Request Schema --------------------------------------------------------

class TranscriptionRequest(BaseModel):
    client_id: str
    # therapist_id is no longer needed in the payload because we get it from the token
    # therapist_id: str 

class TranscriptionResponse(BaseModel):
    detail: str
    # ... other fields as needed


# ----- Route ----------------------------------------------------------------

@router.post("/transcribe/{session_id}", response_model=TranscriptionResponse)
async def run_transcription(
    session_id: str,
    payload: TranscriptionRequest,
    # Use the dependency: this verifies the token, user, and returns the therapist_id
    therapist_id: str = Depends(authenticate)
):
    """
    Validates ownership of client and session, then initiates transcription.
    """
    
    # 1. Validate Client Existence and Ownership (Security Check)
    # This check ensures the client_id provided in the payload belongs to the authenticated therapist.
    client_exists(payload.client_id, therapist_id)

    # 2. Validate Session Ownership (Security Check)
    # This check ensures the session_id belongs to the client AND the authenticated therapist.
    check_session_ownership(session_id, payload.client_id, therapist_id)

    # 3. Perform Transcription (If all security checks pass)
    logger.info(f"[TRANSCRIPTION] Starting session {session_id} for T:{therapist_id}, C:{payload.client_id}")

    result = await transcribe_session(session_id)

    # 4. Return result
    return TranscriptionResponse(
        detail="Transcription completed and further processing started."
    )