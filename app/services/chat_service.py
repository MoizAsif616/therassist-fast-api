import asyncio
from loguru import logger
from fastapi import HTTPException

# Logic Imports
from app.utils.chat_utils import (
    execute_retrieval_pipeline,
    generate_clinical_answer,
    route_query_intent, 
    fetch_client_context
)
from app.utils.db_utils import get_session_number
from app.utils.embedding_utils import generate_query_embedding

async def chat_service(
    query: str,
    client_id: str,
    therapist_id: str,
    session_id: str | None = None
):
    """
    RAG Pipeline (Stage 1: Router Only)
    Analyzes the user's query and returns the execution plan.
    """
    try:
        logger.info(f"[CHAT SERVICE] Processing query for Client {client_id}")

        current_session_number = None
        client_context = await fetch_client_context(client_id)
        
        if session_id:
            try:
                current_session_number = await get_session_number(session_id)
            except Exception as e:
                logger.warning(f"[CHAT SERVICE] Invalid Session ID provided: {e}")
                raise HTTPException(status_code=400, detail="Invalid Session ID provided.")
        try:
            router_plan = await route_query_intent(
                query=query, 
                chat_history=[], 
                current_session_number=current_session_number,
                total_sessions=client_context.get("session_count", 0),
                updated_at=str(client_context.get("updated_at", "")),
                profile=client_context.get("profile", ""),
                emotions=client_context.get("emotions", {})
            )
            logger.success(f"[CHAT SERVICE] Router generated {len(router_plan.sub_queries)} sub-queries.")
            logger.debug(f"[CHAT SERVICE] Router Plan: {router_plan}")
        except Exception as e:
            logger.error(f"[CHAT SERVICE] Router Failure: {e}")
            raise HTTPException(status_code=502, detail="Failed to route query intent.")
        
        try:
            retrieved_context = await execute_retrieval_pipeline(router_plan, client_id)
            logger.success(f"[CHAT SERVICE] Got Context Sequence")
        except:
            logger.error(f"[CHAT SERVICE] Retrieval Failure")
            raise HTTPException(status_code=500, detail="Failed to retrieve context data.")
        
        try:
            logger.info(f"Generating final answer using retrieved context.")
            final_answer = await generate_clinical_answer(retrieved_context, query)
        except Exception as e:
            logger.error(f"[CHAT SERVICE] Generator Failure: {e}")
            raise HTTPException(status_code=500, detail="Failed to generate final answer.")
        
        return final_answer

    except HTTPException as he:
        # Pass through specific HTTP errors (like 502 Bad Gateway from Router)
        raise he
        
    except Exception as e:
        logger.error(f"[CHAT SERVICE] Critical Failure: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error during query processing.")