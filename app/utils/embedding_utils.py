import os
import asyncio
import httpx
from typing import List, Dict, Any, Optional
from fastapi import HTTPException
from loguru import logger
from app.core.supabase_client import get_supabase_client

# --- CONFIGURATION ---
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_MODEL_API_KEY")
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 1))
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/embeddings"
BATCH_SIZE = 10  # Process 50 utterances per API call to save overhead

# --- 1. DATA FETCHING ---

async def fetch_session_data_for_embedding(session_id: str) -> Dict[str, Any]:
    """
    Fetches the session summary, theme, and all related utterances.
    """
    logger.info(f"[EMBEDDING UTILS] Fetching data for session: {session_id}")
    supabase = get_supabase_client()

    try:
        # A. Fetch Session Info (Level 1)
        session_res = supabase.table("sessions").select("summary").eq("id", session_id).single().execute()
        
        # B. Fetch Utterances (Level 2)
        # We only need id, speaker, and text. Order by start_time to keep context logical.
        utterance_res = supabase.table("utterances")\
            .select("id, speaker, utterance")\
            .eq("session_id", session_id)\
            .order("start_time")\
            .execute()

        if not session_res.data:
            raise HTTPException(404, detail=f"Session {session_id} not found.")

        data = {
            "session": session_res.data,
            "utterances": utterance_res.data or []
        }
        
        logger.success(f"[EMBEDDING UTILS] Fetched {len(data['utterances'])} utterances for embedding.")
        return data

    except Exception as e:
        logger.error(f"[EMBEDDING UTILS] DB Fetch Failed: {e}")
        raise HTTPException(500, detail=f"Database error during fetch: {str(e)}")


# --- 2. CORE API HELPER ---

async def _call_embedding_api(texts: List[str]) -> List[List[float]]:
    """
    Internal helper to call OpenRouter Embedding API with retries.
    Handles batch inputs (list of strings).
    """
    if not EMBEDDING_API_KEY:
        raise HTTPException(500, detail="Server Config Error: EMBEDDING_MODEL_API_KEY is missing.")

    headers = {
        "Authorization": f"Bearer {EMBEDDING_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost", # OpenRouter requirement
    }

    payload = {
        "model": EMBEDDING_MODEL_NAME,
        "input": texts 
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(OPENROUTER_BASE_URL, json=payload, headers=headers)
                
                if response.status_code != 200:
                    error_msg = response.text
                    logger.warning(f"[EMBEDDING API] Attempt {attempt} failed: {error_msg}")
                    if attempt == MAX_RETRIES:
                        raise HTTPException(
                            status_code=response.status_code,
                            detail=f"Embedding API Error: {error_msg}"
                        )
                    continue # Retry
                
                result = response.json()
                # OpenRouter/OpenAI returns data in order: data[0].embedding, data[1].embedding...
                embeddings = [item["embedding"] for item in result["data"]]
                return embeddings

        except httpx.RequestError as e:
            logger.warning(f"[EMBEDDING API] Network error on attempt {attempt}: {e}")
            if attempt == MAX_RETRIES:
                raise HTTPException(503, detail="Embedding Service Unavailable (Network Error).")
            await asyncio.sleep(1) # Backoff
            
    return [] # Should not reach here due to raises


# --- 3. EMBEDDING GENERATORS ---

async def generate_summary_embedding(session_data: Dict[str, Any]) -> List[float]:
    """
    Level 1: Generates a single vector for the Session Summary + Theme.
    Format: "Theme: {theme}. Summary: {summary}"
    """
    session = session_data.get("session", {})
    summary = session.get("summary", "") or ""
    theme = session.get("theme", "") or ""

    if not summary and not theme:
        logger.warning("[EMBEDDING UTILS] No summary or theme found. Returning empty vector (or skipping).")
        # In this architecture, if summary is missing, we might return None or handle upstream.
        # Returning None allows the DB transaction to potentially skip this update.
        raise HTTPException(404, detail="No summary or theme available for embedding.") 

    # Contextual Format
    text_to_embed = f"Summary of therapy session: {summary}"
    
    logger.info(f"[EMBEDDING UTILS] Embedding Summary (Length: {len(text_to_embed)} chars)")
    
    vectors = await _call_embedding_api([text_to_embed])
    
    if not vectors:
        raise HTTPException(500, detail="Failed to generate summary embedding.")
        
    return vectors[0]


async def generate_utterance_embeddings_parallel(utterances: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Level 2: Generates vectors for all utterances in parallel batches.
    Format: "{speaker}: {utterance}"
    Returns: List of dicts [{'id': uuid, 'embedding': [0.1, ...]}, ...]
    """
    if not utterances:
        logger.info("[EMBEDDING UTILS] No utterances to embed.")
        raise HTTPException(404, detail="No utterances found for embedding.")

    logger.info(f"[EMBEDDING UTILS] Processing {len(utterances)} utterances in batches of {BATCH_SIZE}...")

    # 1. Prepare Inputs
    # We maintain a mapping of index -> utterance_id to recombine later
    texts_to_embed = []
    utterance_ids = []

    for utt in utterances:
        speaker = utt.get("speaker", "Unknown")
        text = utt.get("utterance", "")
        # Contextual Prefix Format
        formatted_text = f"{speaker} said: {text}"
        
        texts_to_embed.append(formatted_text)
        utterance_ids.append(utt["id"])

    # 2. Create Batches
    tasks = []
    for i in range(0, len(texts_to_embed), BATCH_SIZE):
        batch_texts = texts_to_embed[i : i + BATCH_SIZE]
        tasks.append(_call_embedding_api(batch_texts))

    # 3. Execute Parallel Requests
    # If we have 500 utterances, this runs ~10 parallel requests
    batch_results = await asyncio.gather(*tasks)

    # 4. Flatten Results and Map to IDs
    # batch_results is a List[List[float]] (List of batches of embeddings)
    flat_embeddings = [vec for batch in batch_results for vec in batch]

    if len(flat_embeddings) != len(utterance_ids):
        logger.error(f"[EMBEDDING UTILS] Mismatch! Sent {len(utterance_ids)}, got {len(flat_embeddings)} vectors.")
        raise HTTPException(500, detail="Embedding count mismatch. Integrity check failed.")

    # 5. Construct Result Objects for DB Update
    results = []
    for uid, vector in zip(utterance_ids, flat_embeddings):
        results.append({
            "id": uid,
            "embedding": vector
        })

    logger.success(f"[EMBEDDING UTILS] Successfully generated {len(results)} utterance embeddings.")
    return results


async def generate_query_embedding(query: str) -> List[float]:
    """
    Generates a single vector for a search query.
    Used by the RAG Router/Search endpoints.
    """
    if not query:
        raise HTTPException(400, detail="Query text cannot be empty.")
        
    logger.info(f"[EMBEDDING UTILS] Generating embedding for query: '{query[:30]}...'")
    
    # Reuse the internal helper (wraps query in list)
    vectors = await _call_embedding_api([query])
    
    if not vectors:
        raise HTTPException(500, detail="Failed to generate query embedding.")
        
    # Return the single vector (1536 floats)
    return vectors[0]