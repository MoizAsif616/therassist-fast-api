import asyncio
from loguru import logger
from fastapi import HTTPException

# Logic Imports
from app.core.supabase_client import db
from app.utils.chat_utils import (
    execute_retrieval_pipeline,
    fetch_recent_history,
    format_history_for_llm,
    generate_clinical_answer,
    route_query_intent, 
    fetch_client_context
)
from app.utils.db_utils import get_session_number
from fastapi import BackgroundTasks
from app.utils.chat_utils import generate_chat_summary

async def background_log_chat(session_id: str, query: str, router_plan_dict: dict, answer: str):
    """Background task to generate summary and save to DB."""
    logger.info(f"[BG TASK] Starting summary generation for session {session_id}")
    
    # 1. Get Summary (with fallback built-in)
    summary = await generate_chat_summary(answer["answer"])
    
    # 2. Save to Database
    try:
        db()("chat_logs").insert({
            "session_id": session_id,
            "query": query,
            "router_plan": router_plan_dict,
            "response": answer,
            "summarized_answer": summary
        }).execute()
        logger.success(f"[BG TASK] Chat logged successfully for Session {session_id}")
    except Exception as e:
        logger.error(f"[BG TASK] Failed to log chat: {e}")

async def chat_service(
    query: str,
    client_id: str,
    therapist_id: str,
    background_tasks: BackgroundTasks,
    session_id: str | None = None,
):
    try:
        logger.info(f"[CHAT SERVICE] Processing query for Client {client_id}")
        current_session_number = None
        client_context = await fetch_client_context(client_id)
        
        if session_id:
            try:
                current_session_number_task = get_session_number(session_id)
                recent_history_task = fetch_recent_history(session_id)
                current_session_number, recent_history = await asyncio.gather(
                    current_session_number_task, recent_history_task
                )

                history_str = await format_history_for_llm(recent_history)
                print (history_str)
            except Exception as e:
                logger.warning(f"[CHAT SERVICE] Invalid Session ID provided: {e}")
                raise HTTPException(status_code=400, detail="Invalid Session ID provided. Can't fetch session data")
        try:
            router_plan = await route_query_intent(
                query=query, 
                chat_history=history_str, 
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
            retrieved_context, raw_utterances = await execute_retrieval_pipeline(router_plan, client_id)
            logger.success(f"[CHAT SERVICE] Got Context Sequence")
        except:
            logger.error(f"[CHAT SERVICE] Retrieval Failure")
            raise HTTPException(status_code=500, detail="Failed to retrieve context data.")
        
        try:
            logger.info(f"Generating final answer using retrieved context.")
            # Now it only returns the string directly
            answer = await generate_clinical_answer(retrieved_context, query, history_str)
        except Exception as e:
            logger.error(f"[CHAT SERVICE] Generator Failure: {e}")
            raise HTTPException(status_code=500, detail="Failed to generate final answer.")
        
        logger.debug(f"[CHAT SERVICE] Final Answer Generated.")

        # --- NEW BACKGROUND TASK TRIGGER ---
        if session_id:
            background_tasks.add_task(
                background_log_chat,
                session_id=session_id,
                query=query,
                router_plan_dict=router_plan.dict(),
                answer={"answer": answer, "utterances": raw_utterances}
            )

        # Return immediately to the user!
        return answer, raw_utterances

    except HTTPException as he:
        # Pass through specific HTTP errors (like 502 Bad Gateway from Router)
        raise he
        
    except Exception as e:
        logger.error(f"[CHAT SERVICE] Critical Failure: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error during query processing.")