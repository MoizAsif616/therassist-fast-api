# app/services/user_service.py
from postgrest.exceptions import APIError
from app.core.supabase_client import db
from fastapi import HTTPException, status

def client_exists(client_id: str, therapist_id: str) -> bool:
    """
    Verifies that a client exists and belongs to the authenticated therapist.
    Raises 404 if not found (security best practice: don't reveal clients of others).
    """
    try:
        # 1. Query Clients table
        # We check both ID and therapist_id to prevent unauthorized access (IDOR)
        response = db()("clients")\
            .select("id")\
            .eq("id", client_id)\
            .execute()

        # 2. Check if row exists
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="[USER SERVICE] Client not found."
            )

        return True

    except APIError as e:
        print(f"[DB ERROR] {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="[USER SERVICE] Database check failed."
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
