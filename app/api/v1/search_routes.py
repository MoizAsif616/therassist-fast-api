import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, UUID4
from loguru import logger

# Check if you moved this to app.core or kept it in app.services
# using app.core based on your last snippet
from app.core.supabase_client import get_supabase_client 
from app.utils.embedding_utils import generate_query_embedding

router = APIRouter(tags=["RAG Search Testing"])

# --- Request Model ---
class SearchPayload(BaseModel):
    client_id: UUID4
    query: str

# --- Route 1: Level 2 Search (Specific Quotes) ---
@router.post("/search/utterances")
async def search_utterances_route(payload: SearchPayload):
    """
    Level 2 Search: Finds specific quotes/utterances.
    Returns: Top 3 matches based on semantic similarity.
    """
    logger.info(f"[RAG SEARCH] Searching Utterances for Client {payload.client_id}")

    try:
        # 1. Generate Embedding (Using new util)
        query_vector = await generate_query_embedding(payload.query)

        # 2. Call Supabase RPC
        response = get_supabase_client().rpc(
            "match_utterances",
            {
                "query_embedding": query_vector,
                "match_threshold": 0.5,
                "match_count": 3,
                "filter_client_id": str(payload.client_id)
            }
        ).execute()

        return {"count": len(response.data), "matches": response.data}

    except Exception as e:
        logger.error(f"[RAG SEARCH] Utterance search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Route 2: Level 1 Search (Broad Trends) ---
@router.post("/search/sessions")
async def search_sessions_route(payload: SearchPayload):
    """
    Level 1 Search: Finds broad themes/summaries.
    Returns: Top 1 matching session summary.
    """
    logger.info(f"[RAG SEARCH] Searching Sessions for Client {payload.client_id}")

    try:
        # 1. Generate Embedding
        query_vector = await generate_query_embedding(payload.query)

        # 2. Call Supabase RPC
        response = get_supabase_client().rpc(
            "match_session_summaries",
            {
                "query_embedding": query_vector,
                "match_threshold": 0.0,
                "match_count": 3,
                "filter_client_id": str(payload.client_id)
            }
        ).execute()

        if not response.data:
            return {"message": "No relevant session summaries found."}

        return {"match": response.data[0]}

    except Exception as e:
        logger.error(f"[RAG SEARCH] Session search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))