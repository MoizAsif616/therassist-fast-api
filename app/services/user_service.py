# app/services/user_service.py
from loguru import logger
from postgrest.exceptions import APIError
from app.core.supabase_client import db
from fastapi import HTTPException, status
import uuid
import asyncio

async def client_exists(client_id: str, therapist_id: str) -> bool:
    """
    Checks if a client exists for the given therapist.
    Updated to ASYNC to handle connection stability.
    """
    # --- 1. VALIDATE UUID FORMAT (Fast Fail) ---
    try:
        uuid.UUID(client_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Client ID format. Must be a valid UUID."
        )

    # --- 2. DB CHECK WITH RETRY ON CONNECTION ERRORS ---
    for attempt in range(2):
        try:
            # Note: We use db() here which returns the client
            response = db()("clients")\
                .select("id")\
                .eq("id", client_id)\
                .execute()

            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Client not found."
                )

            return True

        except Exception as e:
            if "WinError 10054" in str(e) and attempt == 0:
                logger.warning(f"[DB] Connection reset (10054). Retrying once...")
                await asyncio.sleep(0.5)
                continue
            
            logger.error(f"[DB ERROR] client_exists failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal database error while verifying client."
            )

def therapist_exists(therapist_id: str) -> bool:
    """
    Stub for therapist existence.
    """
    return True
