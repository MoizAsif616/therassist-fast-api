from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger

# Schemas
from app.schemas.chat_schemas import ChatRequest, ChatResponse

# Services & Dependencies
from app.services.auth_service import authenticate
from app.services.user_service import client_exists
from app.services.db_service import check_session_ownership
from app.services.chat_service import chat_service

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    payload: ChatRequest,
    therapist_id: str = Depends(authenticate)
):
    """
    Clinical RAG Chat Interface.
    
    - **Authentication**: Verified via JWT.
    - **Authorization**: Checks if Therapist has access to the requested Client.
    - **Context**: Can be Global (All Sessions) or Local (Specific Session ID).
    """
    
    # 1. Security Check: Client Access
    # Ensure this therapist is allowed to view this client's data
    if not client_exists(payload.client_id, therapist_id):
        logger.warning(f"[CHAT ROUTE] Access Denied. T:{therapist_id} -> C:{payload.client_id}")
        raise HTTPException(
            status_code=403, 
            detail="You do not have permission to access this client's data."
        )

    # 2. Context Check: Session Access (Optional)
    # If the user is chatting *inside* a specific session view, verify ownership
    if payload.session_id:
        try:
            check_session_ownership(payload.session_id, payload.client_id, therapist_id)
        except HTTPException:
            logger.warning(f"[CHAT ROUTE] Session Accessd denied.")
            raise HTTPException(
                status_code=400, 
                detail="The specified session does not belong to this client."
            )
    else:
        logger.error(f"[CHAT ROUTE] Invalid session id")
        raise HTTPException(
            status_code=400, 
            detail="Invalid session id."
        )

    logger.info(f"[CHAT ROUTE] Query received from T:{therapist_id}")

    # 3. Execute Service
    result = await chat_service(payload, therapist_id)

    return result