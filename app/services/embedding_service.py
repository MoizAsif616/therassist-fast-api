import asyncio
from loguru import logger
from fastapi import HTTPException
from app.services.db_service import get_session
# Import new utils
from app.utils.embedding_utils import (
    fetch_session_data_for_embedding,
    generate_summary_embedding,
    generate_utterance_embeddings_parallel
)
from app.utils.transaction_utils import commit_embedding_transaction

async def embedding_service(session_id: str):
    """
    Orchestrates the RAG Embedding phase:
    1. Fetches Session Summary & Utterances.
    2. Generates Embeddings in Parallel (Summary + Utterances).
    3. Commits all vectors to Supabase.
    """
    
    # 1. Validate State
    # Note: Optimization - We could move this check inside the fetch util to save 1 DB call,
    # but keeping it here for explicit flow control is fine.
    session = get_session(session_id)
    if session["processing_state"] != "ANNOTATED":
        logger.warning(f"[EMBEDDING SERVICE] Cannot process session {session_id} (state: {session['processing_state']})")
        raise HTTPException(400, detail="Session is not in ANNOTATED state.")

    logger.info(f"[EMBEDDING SERVICE] Starting RAG embedding generation for {session_id}")

    # 2. Fetch Data
    try:
        # ✅ FIX: Do not unpack. Assign to a variable.
        data_payload = await fetch_session_data_for_embedding(session_id)
        
        # Extract specific lists/dicts needed
        utterances = data_payload.get("utterances", [])
        
    except Exception as e:
        logger.error(f"[EMBEDDING SERVICE] Data fetch failed: {e}")
        raise HTTPException(500, detail="Failed to fetch session data for embedding.")

    if not utterances:
        logger.warning(f"[EMBEDDING SERVICE] No utterances found for session {session_id}")
        raise HTTPException(404, detail="No utterances found to embed.")

    try:
        # 3. Parallel Execution
        logger.info(f"[EMBEDDING SERVICE] Launching parallel embedding tasks...")

        # Task A: Embed Session Summary (Pass the whole payload, util extracts 'session' key)
        summary_task = generate_summary_embedding(data_payload)
        
        # Task B: Embed Utterances
        utterances_task = generate_utterance_embeddings_parallel(utterances)

        # Wait for both to complete
        summary_embedding, embedded_utterances = await asyncio.gather(
            summary_task,
            utterances_task
        )
        
        logger.success(f"[EMBEDDING SERVICE] All embeddings generated successfully.")

        # 4. Transaction Commit
        logger.info(f"[EMBEDDING SERVICE] Committing to Database...")
        
        # Ensure your transaction utils accepts these arguments
        commit_embedding_transaction(
            session_id=session_id,
            summary_embedding=summary_embedding,
            utterances=embedded_utterances
        )

        return {"detail": "Embedding phase completed.", "session_id": session_id}

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"[EMBEDDING SERVICE] Process Failed: {e}")
        raise HTTPException(500, detail=f"Embedding service processing failed: {e}")