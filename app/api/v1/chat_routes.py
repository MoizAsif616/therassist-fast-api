from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from typing import List, Any
from app.schemas.chat_schemas import ChatRequest, RouterOutput 

# Services & Dependencies
from app.services.auth_service import authenticate
from app.services.user_service import client_exists
from app.services.db_service import check_session_ownership
from app.services.chat_service import chat_service

router = APIRouter()

@router.post("/chat", response_model=str) # Updated to return the Plan
async def chat_endpoint(
    payload: ChatRequest,
    therapist_id: str = Depends(authenticate)
):
    
    if not client_exists(payload.client_id, therapist_id):
        logger.warning(f"[CHAT ROUTE] Access Denied. T:{therapist_id} -> C:{payload.client_id}")
        raise HTTPException(
            status_code=403, 
            detail="You do not have permission to access this client's data."
        )

    if payload.session_id:
        try:
            check_session_ownership(payload.session_id, payload.client_id, therapist_id)
        except HTTPException:
            logger.warning(f"[CHAT ROUTE] Session Access denied for {payload.session_id}")
            raise HTTPException(
                status_code=400, 
                detail="The specified session does not belong to this client."
            )
    else:
        logger.error(f"[CHAT ROUTE] No session_id provided.")
        raise HTTPException(
            status_code=400, 
            detail="No session_id provided."
        )

    logger.info(f"[CHAT ROUTE] Query received from T:{therapist_id}")

    result = await chat_service(
        query=payload.query,
        client_id=payload.client_id,
        therapist_id=therapist_id,
        session_id=payload.session_id
    )

    return result