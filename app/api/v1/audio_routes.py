# app/api/v1/audio_routes.py

from fastapi import (
    APIRouter, UploadFile, File, Form, HTTPException,
    Header, BackgroundTasks, Depends
)
from loguru import logger
from pydantic import BaseModel, ValidationError
import json

from app.services.auth_service import *
from app.services.db_service import client_exists
from app.services.audio_service import audio_service


router = APIRouter()

class AudioUploadRequest(BaseModel):
    client_id: str
    # therapist_id: str


class AudioUploadResponse(BaseModel):
    # status: str
    session_id: str
    detail: str

## MAIN ROUTE
@router.post("/upload", status_code=201, response_model=AudioUploadResponse)
async def upload_audio(
    background_tasks: BackgroundTasks,
    audio_file: UploadFile = File(...),
    payload: str = Form(...),
    therapist_id: str = Depends(authenticate)
):
    try:
        metadata = AudioUploadRequest(**json.loads(payload))
    except (json.JSONDecodeError, ValidationError):
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    ## CHECKING IF CLIENT EXISTS
    if not client_exists(metadata.client_id):
        raise HTTPException(status_code=400, detail="Client does not exist")

    ## CALL AUDIO SERVICE
    logger.info(f"[AUDIO UPLOAD] Starting audio service.")
    session_id = audio_service(
        file=audio_file,
        client_id=metadata.client_id,
        therapist_id=therapist_id,    
    )

    return AudioUploadResponse(
        session_id=session_id,
        detail="Audio uploaded successfully. Processing will start shortly"
    )
