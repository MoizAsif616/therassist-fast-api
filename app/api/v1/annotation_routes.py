# app/api/v1/annotation_routes.py

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from loguru import logger

from app.services.auth_service import authorize
from app.services.db_service import get_session, client_exists, therapist_exists
from app.services.annotation_service import annotation_service

router = APIRouter()


# ---------------------- REQUEST SCHEMA ----------------------

class AnnotationRequest(BaseModel):
    client_id: str
    therapist_id: str


# ---------------------- RESPONSE SCHEMA ----------------------

class AnnotationResponse(BaseModel):
    session_id: str
    message: str


# ---------------------- ROUTE HANDLER -----------------------

@router.post("/annotate/{session_id}", response_model=AnnotationResponse)
async def run_annotation(
    session_id: str,
    payload: AnnotationRequest,
    authorization: str = Header(...)
):
    """
    Validate → authorization → ownership → call annotation_service
    """

    # --- Validate Authorization Header ---
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Invalid authorization header format")

    token = authorization.replace("Bearer ", "").strip()

    if not authorize(token):
        raise HTTPException(401, "Unauthorized")

    # --- Validate Provided Client & Therapist ---
    if not client_exists(payload.client_id):
        raise HTTPException(400, "Client does not exist")

    if not therapist_exists(payload.therapist_id):
        raise HTTPException(400, "Therapist does not exist")

    # --- Validate Session Ownership ---
    session = get_session(session_id)

    if session["client_id"] != payload.client_id:
        raise HTTPException(403, "Session does not belong to this client")

    if session["therapist_id"] != payload.therapist_id:
        raise HTTPException(403, "Session does not belong to this therapist")

    logger.info(f"[ANNOTATION] Route triggered annotation for session {session_id}")

    # --- Call annotation logic ---
    result = await annotation_service(session_id)

    return AnnotationResponse(
        session_id=session_id,
        message=result["status"]
    )
