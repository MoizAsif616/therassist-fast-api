# app/api/v1/audio_routes.py

from fastapi import (
    APIRouter, UploadFile, File, Form, HTTPException,
    Header, BackgroundTasks
)
from pydantic import BaseModel, ValidationError
import json

from app.services.auth_service import authorize
from app.services.db_service import client_exists, therapist_exists
from app.services.audio_service import process_audio_and_create_session
# from app.services.transcription_service import start_transcription


router = APIRouter()


# --------------------------
# Request & Response Schemas
# --------------------------

class AudioUploadRequest(BaseModel):
    client_id: str
    therapist_id: str


class AudioUploadResponse(BaseModel):
    status: str
    session_id: str
    message: str


# --------------------------
# Upload Route
# --------------------------

@router.post("/upload", status_code=201, response_model=AudioUploadResponse)
async def upload_audio(
    background_tasks: BackgroundTasks,
    audio_file: UploadFile = File(...),
    payload: str = Form(...),
    authorization: str = Header(...)
):
    # ---- Validate Auth Token ----
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header format")

    token = authorization.replace("Bearer ", "").strip()

    if not authorize(token):
        raise HTTPException(status_code=401, detail="Unauthorized")

    # ---- Parse JSON Payload ----
    try:
        metadata = AudioUploadRequest(**json.loads(payload))
    except (json.JSONDecodeError, ValidationError):
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # ---- Validate Client & Therapist ----
    if not client_exists(metadata.client_id):
        raise HTTPException(status_code=400, detail="Client does not exist")

    if not therapist_exists(metadata.therapist_id):
        raise HTTPException(status_code=400, detail="Therapist does not exist")

    # ---- Process Audio & Create Session ----
    session_id = process_audio_and_create_session(
        file=audio_file,
        client_id=metadata.client_id,
        therapist_id=metadata.therapist_id,
    )

    # ---- Success Response ----
    return AudioUploadResponse(
        status="uploaded",
        session_id=session_id,
        message="Audio processed and pipeline started."
    )
