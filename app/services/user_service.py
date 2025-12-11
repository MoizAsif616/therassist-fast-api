# app/services/user_service.py

def client_exists(client_id: str) -> bool:
    """
    Placeholder check for client existence.
    
    Later:
    - query Supabase 'Clients' table
    - verify therapist has access to this client
    """
    print(f"[CLIENT] Checking client {client_id}")
    print("[CLIENT] Client exists (stub).")
    return True


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
