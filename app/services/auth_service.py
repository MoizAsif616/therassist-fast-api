# app/services/auth_service.py

def authorize(token: str) -> bool:
    """
    Placeholder for request authentication.
    
    Later: 
    - validate JWT or Supabase Auth token
    - check expiry, permissions
    - verify therapist session ownership, etc.
    """
    print(f"[AUTH] Verifying token: {token}")

    # For now, always treat as authorized
    print("[AUTH] Authorized request (stub).")
    return True
