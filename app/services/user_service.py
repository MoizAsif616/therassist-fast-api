# app/services/user_service.py
from asyncio.log import logger
from postgrest.exceptions import APIError
from app.core.supabase_client import db
from fastapi import HTTPException, status
import uuid

def client_exists(client_id: str, therapist_id: str) -> bool:
    # --- 1. VALIDATE UUID FORMAT (Fast Fail) ---
    try:
        uuid.UUID(client_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Client ID format. Must be a valid UUID."
        )
    try:
        response = db()("clients")\
            .select("id")\
            .eq("id", client_id)\
            .execute()

        # --- 3. CHECK EXISTENCE ---
        if not response.data:
            # Valid UUID format, but no matching row found
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Client not found."
            )

        return True

    except APIError as e:
        # Log the actual DB error for debugging (don't show to user)
        logger.error(f"[DB ERROR] client_exists failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal database error while verifying client."
        )


def therapist_exists(therapist_id: str) -> bool:
    """
    Placeholder check for therapist existence.
    
    Later:
    - verify therapist account in Supabase Auth
    - check therapist has permissions
    """
    print(f"[THERAPIST] Checking therapist {therapist_id}")
    print("[THERAPIST] Therapist exists (stub).")
    return True
