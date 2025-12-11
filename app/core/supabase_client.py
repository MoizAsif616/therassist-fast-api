# app/core/supabase_client.py
from typing import Any
import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()  # loads .env in project root

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_KEY in .env")

_supabase_client: Client | None = None

def get_supabase_client() -> Client:
    """Singleton supabase client used for both Postgres (from) and Storage operations."""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client

def db():
    """Convenience accessor for PostgREST / table operations via supabase client."""
    return get_supabase_client().from_

storage = get_supabase_client().storage
