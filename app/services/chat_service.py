import asyncio
from loguru import logger
from fastapi import HTTPException

# Schema Imports
from app.schemas.chat_schemas import ChatRequest, ChatResponse, Source

# Logic Imports
from app.utils.chat_utils import (
    route_query_intent, 
    execute_retrieval, 
    generate_clinical_answer,
    fetch_client_context
)
from app.utils.transaction_utils import commit_chat_history_transaction
from app.utils.db_utils import get_session_number

async def chat_service(
    request: ChatRequest,
    therapist_id: str
) -> ChatResponse:
    """
    Strict RAG Pipeline. 
    Raises HTTPExceptions immediately if Router or Generator fails.
    """
    try:
        logger.info(f"[CHAT SERVICE] Processing query for Client {request.client_id}")

        # 0. Context Prep
        current_session_number = None
        if request.session_id:
            current_session_number, client_context = await asyncio.gather(
                get_session_number(request.session_id),
                fetch_client_context(request.client_id)
            )

        router_plan = await route_query_intent(
            query=request.query, 
            chat_history=request.chat_history, 
            current_session_number=current_session_number,
            total_sessions=client_context.get("session_count"),
            updated_at=client_context.get("updated_at"),
            profile=client_context.get("profile"),
            emotions=client_context.get("emotions")
        )
        
        logger.info(f"[CHAT SERVICE] Router Plan: {router_plan}")
        # 2. SHORT CIRCUIT (Irrelevant Query)
        # if not router_plan.is_relevant:
        #     logger.info("[CHAT SERVICE] Query deemed irrelevant.")
        #     refusal_msg = router_plan.direct_response or "I can only assist with therapeutic analysis."
            
        #     # Log the rejection
        #     commit_chat_history_transaction(
        #         session_id=request.session_id or "global",
        #         client_id=request.client_id,
        #         therapist_id=therapist_id,
        #         query=request.query,
        #         answer=refusal_msg,
        #         sources=[]
        #     )
        #     return ChatResponse(answer=refusal_msg, sources=[])

        # # 3. RETRIEVAL
        # context_data = await execute_retrieval(router_plan, request.client_id, request.query)
        
        # # 4. GENERATION
        # # If Generator fails (429/500), it raises Exception here.
        # answer_text = await generate_clinical_answer(request.query, context_data, client_context)
        
        # # 5. LOGGING & RESPONSE
        # final_sources = [
        #     Source(
        #         source_type=item.get("source_type", "text"),
        #         session_number=item.get("session_number", 0),
        #         sequence_number=item.get("sequence_number"),
        #         timestamp=str(item.get("start_seconds", 0)),
        #         confidence=item.get("score", 1.0)
        #     ) for item in context_data
        # ]

        # commit_chat_history_transaction(
        #     session_id=request.session_id or "global",
        #     client_id=request.client_id,
        #     therapist_id=therapist_id,
        #     query=request.query,
        #     answer=answer_text,
        #     sources=[s.dict() for s in final_sources]
        # )

        logger.success(f"[CHAT SERVICE] Answered for Client {request.client_id}")

        return ChatResponse(
            answer="answer_text",
            # sources=final_sources,
            sources=[],
            # meta_data={"strategy": router_plan.rag_strategy.dict()}
            meta_data=None
        )

    except HTTPException as he:
        # 1. Pass through specific HTTP errors (like 429 Too Many Requests)
        # This ensures the Frontend gets the exact error code.
        raise he
        
    except Exception as e:
        # 2. Catch unexpected server crashes and return 500
        logger.error(f"[CHAT SERVICE] Critical Failure: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error during chat processing.")