from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from loguru import logger

# Import Authentication and Validation Services
from app.services.auth_service import authenticate
from app.services.db_service import check_session_ownership
from app.services.user_service import client_exists

# Import the Embedding Service (we will create this next)
from app.services.embedding_service import embedding_service

router = APIRouter()

class EmbeddingRequest(BaseModel):
    client_id: str

class EmbeddingResponse(BaseModel):
    detail: str


@router.post("/embed/{session_id}", response_model=EmbeddingResponse)
async def trigger_embedding_generation(
    session_id: str,
    payload: EmbeddingRequest,
    therapist_id: str = Depends(authenticate)
):
    """
    Triggers the generation of vector embeddings for a specific session.
    Validates ownership before processing.
    """

    client_exists(payload.client_id, therapist_id)
    check_session_ownership(session_id, payload.client_id, therapist_id)

    try:
        logger.info(f"[EMBEDDING ROUTE] Initiating embedding generation for Session {session_id} (Client: {payload.client_id})")

        await embedding_service(session_id)

        return EmbeddingResponse(
            detail="Embedding generation completed successfully."
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"[EMBEDDING ROUTE] Unexpected Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error during embedding generation.")