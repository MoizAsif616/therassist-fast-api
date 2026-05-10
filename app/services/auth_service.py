import os
import jwt
from fastapi import Header, HTTPException, status
from dotenv import load_dotenv
from postgrest.exceptions import APIError

from app.core.supabase_client import db

# 1. Setup & Config
load_dotenv()
SUPABASE_JWT_SECRET = os.getenv("JWT_SECRET")

# Ensure 'supabase' client is imported here. 
# from main import supabase  <-- UNCOMMENT THIS LINE in your actual code

def authenticate(authorization: str = Header(..., description="Bearer <token>")) -> str:
    """
    1. Validates JWT.
    2. Maps User UUID -> Therapist UUID via Database.
    3. Returns: therapist_id (str)
    """

    # --- PHASE 1: JWT VALIDATION (CPU Bound) ---
    if not SUPABASE_JWT_SECRET:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server Config Error: JWT Secret missing.")

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid header. Format: 'Bearer <token>'")

    try:
        token = authorization.replace("Bearer ", "").strip()
        
        # Decode using Legacy HS256 Secret
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
            options={"verify_exp": True}
        )
        
        user_uuid = payload.get("sub")
        if not user_uuid:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token valid but missing User ID.")

    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Session expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

    # --- PHASE 2: DATABASE LOOKUP (IO Bound) ---
    # FastAPI runs 'def' functions in a threadpool, so this blocking call won't freeze your server.
    try:
        # Fetch Therapist ID linked to this User UUID
        response = db()("therapists")\
            .select("id")\
            .eq("user_id", user_uuid)\
            .single()\
            .execute()
        
        therapist_id = response.data.get("id")
        
        if not therapist_id:
             raise HTTPException(status.HTTP_403_FORBIDDEN, detail="User is not a registered Therapist.")
             
        return therapist_id

    except APIError as e:
        # Code 'PGRST116' means 0 rows found (User exists, but not in Therapist table)
        if e.code == "PGRST116":
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access Denied: Therapist profile not found.")
        print(f"[DB ERROR] {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database lookup failed.")
    except Exception as e:
        print(f"[SYSTEM ERROR] {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Authentication failed.")

    # return "b6ce3015-9f05-4bc2-b1fd-36e05a4d9023"




def authorize(token: str) -> bool:
    """
    Placeholder for request authentication.
    
    Later: 
    - validate JWT or Supabase Auth token
    - check expiry, permissions
    - verify therapist session ownership, etc.
    """
    print(f"[AUTH] Verifying token: {token}")
    if token != "ding-dong":
        print("[AUTH] Unauthorized request.")
        return False
    # For now, always treat as authorized
    print("[AUTH] Authorized request (stub).")
    return True
