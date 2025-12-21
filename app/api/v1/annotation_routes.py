# app/api/v1/annotation_routes.py

from fastapi import APIRouter, Header, HTTPException, status, Depends
from pydantic import BaseModel
from loguru import logger

# Import the necessary dependencies and service functions
from app.services.auth_service import authenticate
from app.services.db_service import check_session_ownership
from app.services.user_service import client_exists
from app.services.annotation_service import annotation_service


router = APIRouter()


# ---------------------- REQUEST SCHEMA ----------------------

class AnnotationRequest(BaseModel):
    client_id: str
    # Removed redundant therapist_id as it is derived securely from the token


# ---------------------- RESPONSE SCHEMA ----------------------

class AnnotationResponse(BaseModel):
    session_id: str
    detail: str


# ---------------------- ROUTE HANDLER -----------------------

@router.post("/annotate/{session_id}", response_model=AnnotationResponse)
async def run_annotation(
    session_id: str,
    payload: AnnotationRequest,
    # Use the Dependency: This handles JWT validation, therapist existence check,
    # and returns the therapist_id if successful.
    therapist_id: str = Depends(authenticate)
):
    """
    Validates ownership of client and session, then initiates annotation.
    """

    client_exists(payload.client_id, therapist_id)

    check_session_ownership(session_id, payload.client_id, therapist_id)

    logger.info(f"[ANNOTATION] Route triggered annotation for session {session_id} for T:{therapist_id}, C:{payload.client_id}")

    result = await annotation_service(session_id)

    # 4. Return result
    return AnnotationResponse(
        session_id=session_id,
        detail="Annotation completed and further processing started."
    )