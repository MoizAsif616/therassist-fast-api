import os
import json
import re
import httpx
import asyncio
from typing import List, Dict, Any, Optional
from loguru import logger
from fastapi import HTTPException

# Project Imports
from app.core.supabase_client import get_supabase_client
from app.schemas.chat_schemas import RouterOutput, Scope, Filters
from app.utils.promt_templates import ROUTER_SYSTEM_PROMPT, CLINICAL_GENERATOR_SYSTEM_PROMPT
from app.utils.embedding_utils import generate_query_embedding

# --- CONFIGURATION ---
CHAT_MODEL_API_KEY = os.getenv("MODEL_API_KEY")
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"

# Model Selection
ROUTER_MODEL = os.getenv("CHAT_MODEL_NAME")
GENERATOR_MODEL = os.getenv("CHAT_MODEL_NAME")

supabase = get_supabase_client()


# ==============================================================================
# 0. HELPER: Robust API Call (Raises HTTP Exceptions)
# ==============================================================================

# async def _call_llm_api(
#     messages: List[Dict], 
#     model: str,
#     json_mode: bool = False, 
#     temperature: float = 0.0
# ) -> str:
#     """
#     Robust HTTPX call. Raises specific HTTPExceptions on failure.
#     """
#     headers = {
#         "Authorization": f"Bearer {CHAT_MODEL_API_KEY}",
#         "HTTP-Referer": "https://therassist.app",
#         "X-Title": "Therassist",
#         "Content-Type": "application/json"
#     }
    
#     # Ensure model is a string (Fixes the pyexpat.model crash)
#     if not isinstance(model, str):
#         logger.error(f"Invalid model type passed: {type(model)}. Expected str.")
#         raise HTTPException(status_code=500, detail="Internal Configuration Error: Invalid Model Type")

#     payload = {
#         "model": model,
#         "messages": messages,
#         "temperature": temperature,
#         "stream": False
#     }
    
#     # GOOGLE GEMMA/GEMINI FIX: They usually do NOT support 'json_object' mode.
#     # We only enable it for non-Google models to prevent 400 Bad Request.
#     if json_mode and "google" not in model.lower() and "gemma" not in model.lower():
#         payload["response_format"] = {"type": "json_object"}

#     # Increased timeout for complex queries
#     async with httpx.AsyncClient(timeout=120.0) as client:
#         # RETRY LOOP: Try 3 times
#         for attempt in range(2):
#             try:
#                 resp = await client.post(OPENROUTER_CHAT_URL, headers=headers, json=payload)
                
#                 # HANDLING RATE LIMITS (429)
#                 if resp.status_code == 429:
#                     wait_time = 5 * (2 ** attempt) # Aggressive: 5s, 10s, 20s
#                     logger.warning(f"[LLM API] Rate Limit (429) on {model}. Retrying in {wait_time}s...")
#                     await asyncio.sleep(wait_time)
#                     continue
                
#                 # HANDLING SERVICE DOWN (502/503)
#                 if resp.status_code >= 500:
#                     logger.warning(f"[LLM API] Service Error {resp.status_code}. Retrying in 2s...")
#                     await asyncio.sleep(2)
#                     continue

#                 resp.raise_for_status()
#                 result = resp.json()
                
#                 if not result.get("choices"):
#                     raise HTTPException(status_code=502, detail=f"OpenRouter returned empty choices for {model}")

#                 # CLEANER (DeepSeek <think> tag removal)
#                 content = result["choices"][0]["message"]["content"]
#                 if "<think>" in content:
#                     content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                
#                 return content
                
#             except httpx.HTTPStatusError as e:
#                 # Fatal errors that shouldn't be retried (e.g., 400 Bad Request, 401 Unauthorized)
#                 if e.response.status_code not in [429, 502, 503]:
#                     logger.error(f"[LLM API] Fatal Error {e.response.status_code}: {e.response.text}")
#                     # Map 429 to 503 Service Unavailable for the frontend
#                     status = 401 if e.response.status_code == 401 else 502
#                     raise HTTPException(status_code=status, detail=f"LLM Provider Error: {e.response.text}")
            
#             except Exception as e:
#                 logger.error(f"[LLM API] Connection Exception: {e}")
#                 if attempt == 2:
#                     raise HTTPException(status_code=504, detail="AI Service Timed Out (Gateway Timeout)")

#     # If loop finishes without return
#     raise HTTPException(status_code=503, detail="AI Service Busy. Maximum retries exceeded.")

CHAT_MODEL_API_KEY = os.getenv("CHAT_MODEL_API_KEY")
# Groq API Endpoint
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

async def _call_llm_api(
    messages: List[Dict], 
    model: str,
    json_mode: bool = False, 
    temperature: float = 0.0
) -> str:
    """
    Robust HTTPX call to Groq. Raises specific HTTPExceptions on failure.
    Tried ONLY ONCE (No Retries).
    """
    headers = {
        "Authorization": f"Bearer {CHAT_MODEL_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Ensure model is a string
    if not isinstance(model, str):
        logger.error(f"Invalid model type passed: {type(model)}. Expected str.")
        raise HTTPException(status_code=500, detail="Internal Configuration Error: Invalid Model Type")

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False
    }
    
    # GROQ SPECIFIC: Supports 'json_object' for Llama 3 models.
    # Note: Groq requires the word "json" to appear in the system prompt for this to work.
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    # Increased timeout for complex queries
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            # Single Attempt (No Loop)
            resp = await client.post(GROQ_CHAT_URL, headers=headers, json=payload)
            
            # HANDLING RATE LIMITS (429) - Immediate Fail since no retries
            if resp.status_code == 429:
                logger.warning(f"[LLM API] Rate Limit (429) on {model}.")
                raise HTTPException(status_code=503, detail="AI Service Busy (Rate Limit). Please try again.")
            
            # HANDLING SERVICE DOWN (502/503)
            if resp.status_code >= 500:
                logger.warning(f"[LLM API] Service Error {resp.status_code}.")
                raise HTTPException(status_code=502, detail="AI Service Temporarily Unavailable.")

            resp.raise_for_status()
            result = resp.json()
            
            if not result.get("choices"):
                raise HTTPException(status_code=502, detail=f"Groq returned empty choices for {model}")

            # CLEANER
            content = result["choices"][0]["message"]["content"]
            
            # (Optional) DeepSeek <think> tag removal if you ever switch models
            if "<think>" in content:
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            
            return content
            
        except httpx.HTTPStatusError as e:
            # Fatal errors (e.g., 400 Bad Request, 401 Unauthorized)
            logger.error(f"[LLM API] Fatal Error {e.response.status_code}: {e.response.text}")
            status = 401 if e.response.status_code == 401 else 502
            raise HTTPException(status_code=status, detail=f"LLM Provider Error: {e.response.text}")
        
        except httpx.RequestError as e:
            # Network level errors (DNS, Timeout, etc.)
            logger.error(f"[LLM API] Connection Exception: {e}")
            raise HTTPException(status_code=504, detail="AI Service Connection Failed (Gateway Timeout)")
        
        except Exception as e:
            # Unexpected Python level errors
            logger.error(f"[LLM API] Unexpected Error: {e}")
            raise HTTPException(status_code=500, detail="Internal Server Error during AI processing.")


# ==============================================================================
# 1. INTELLIGENCE LAYER (LLM Router)
# ==============================================================================

async def route_query_intent(
    query: str, 
    chat_history: List[dict], 
    current_session_number: int, 
    total_sessions: int, 
    updated_at: str, 
    profile: str, 
    emotions: Any
) -> RouterOutput:
    """
    Uses LLM to decompose and classify intent into a Master Execution Plan.
    STRICT MODE: Raises exception on failure.
    """
    logger.info(f"[ROUTER] Analyzing with {ROUTER_MODEL}...")
    
    # 1. Prepare Chat History (Limit to last 2 turns to keep focus tight)
    # history_text = "\n".join([f"{msg.get('role', 'user')}: {msg.get('content', '')}" for msg in chat_history[-2:]])
    
    # 2. Prepare Dynamic System Context (CRITICAL for 'Router Known' queries)
    # We format the emotion map nicely if it's a dict, otherwise stringify it.
    # formatted_emotions = json.dumps(emotions, indent=2) if isinstance(emotions, (dict, list)) else str(emotions)

    # context_instruction = f"""
    # ### 7. CURRENT SYSTEM CONTEXT (DYNAMIC)
    # Use the data below to answer "Router Known" queries immediately.
    # - Current Session Number: {current_session_number}
    # - Total Sessions: {total_sessions}
    # - Client Profile Summary: {profile}
    # - Client Aggregated Emotion Map: {formatted_emotions}
    # - Knowledge Base Last Updated: {updated_at}
    
    # """
    context_instruction = f"""
    Carefully analyze the query and divide into questions being asked. Questions can be seperated by commas, "and", "then", "after that" or even implicit intent etc.
    Current Session Number: {current_session_number}
    Total Sessions: {total_sessions}
    Session are numbered starting from 1 onwards.
    Last session added to knowledge-base on: {updated_at}
    NOTE: STRICTLY FOLLOW THE OUTPUT FORMAT INSTRCUTIONS
    """
    # 3. Construct the User Message
    user_message_content = (
        f"{context_instruction}\n\n"
        # f"Chat History:\n{history_text}\n\n"
        f"Current Query: {query}"
    )
    
    messages = [
        {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
        {"role": "user", "content": user_message_content}
    ]

    # 4. Call LLM (Strict Mode)
    # We allow the exception from _call_llm_api to bubble up if API fails.
    content = await _call_llm_api(messages, model=ROUTER_MODEL, json_mode=True, temperature=0.0)
    
    # 5. Parse & Validate
    try:
        # aggressive cleanup for markdown blocks often returned by smaller models
        if "```" in content:
            match = re.search(r"```(?:json)?(.*?)```", content, re.DOTALL)
            if match:
                content = match.group(1).strip()
        
        data = json.loads(content)
        
        # Validate against our new Master Schema Pydantic Model
        return RouterOutput(**data)

    except json.JSONDecodeError:
        logger.error(f"[ROUTER] Invalid JSON received: {content}")
        raise HTTPException(status_code=502, detail="AI Router returned invalid JSON format.")
    except Exception as e:
        logger.error(f"[ROUTER] Pydantic Validation Error: {e}")
        # Log the actual data that failed validation for debugging
        logger.debug(f"[ROUTER] Failed Payload: {content}")
        raise HTTPException(status_code=502, detail="AI Router output did not match required schema.")


# ==============================================================================
# 2. GENERATION LAYER (Clinical Answer)
# ==============================================================================

async def generate_clinical_answer(query: str, context_data: List[Dict], client_context: Dict[str, Any]) -> str:
    """
    Uses LLM to generate answer. STRICT MODE: Raises exception on failure.
    """
    context_str = ""
    for i, item in enumerate(context_data):
        score = item.get("score", 0.0)
        context_str += f"[{i+1}] Session {item.get('session_number', '?')} ({item.get('speaker')}): {item.get('text')} (Rel: {score:.2f})\n"

    if not context_str:
        context_str = "No specific records found matching the criteria."

    emotions_str = json.dumps(client_context.get("emotions", {}), indent=2)

    system_prompt = f"""{CLINICAL_GENERATOR_SYSTEM_PROMPT}

    === PATIENT CONTEXT ===
    Profile: {client_context.get("profile")}
    
    Long-Term Emotional Baseline (Frequency across all sessions):
    {emotions_str}
    =======================
    """

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Retrieved Data:\n{context_str}\n\nQuestion: {query}"}
    ]

    # STRICT CALL: No try/except block.
    return await _call_llm_api(messages, model=GENERATOR_MODEL, json_mode=False, temperature=0.3)


# ==============================================================================
# 3. RETRIEVAL LAYER (Database)
# ==============================================================================

async def fetch_client_context(client_id: str) -> Dict[str, Any]:
    try:
        response = supabase.table("client_insights")\
            .select("clinical_profile, emotion_map", "session_count", "updated_at")\
            .eq("client_id", client_id)\
            .maybe_single()\
            .execute()
        
        if response.data:
            return {
                "profile": response.data.get("clinical_profile") or "No clinical profile available.",
                "emotions": response.data.get("emotion_map") or {},
                "session_count": response.data.get("session_count") or 0,
                "updated_at": response.data.get("updated_at")
            }
        return {"profile": "No profile data found.", "emotions": {}}

    except Exception as e:
        logger.warning(f"[CONTEXT FETCH] Failed to fetch client insights: {e}")
        return {"profile": "Profile temporarily unavailable.", "emotions": {}}

async def execute_retrieval(router_plan: RouterOutput, client_id: str, query_text: str) -> List[Dict]:
    strategy = router_plan.rag_strategy
    filters = router_plan.filters
    scope = router_plan.scope
    
    logger.info(f"[RAG] Executing Mode: {strategy.execution_mode}")

    if strategy.execution_mode == "count_only":
        return [{"text": "Found multiple matches.", "count": 0}] 

    if strategy.execution_mode == "full_fetch_as_is":
        return [{"text": "Session Summary Placeholder", "speaker": "System"}]

    # Vector Search
    query_vector = await generate_query_embedding(query_text)
    hits = await _search_supabase_vectors(query_vector, filters, scope, client_id)
    
    if strategy.relational_logic == "next_utterance":
        return await _sql_hop(hits, offset=1)
    elif strategy.relational_logic == "previous_utterance":
        return await _sql_hop(hits, offset=-1)
    
    return hits

async def _search_supabase_vectors(vector: List[float], filters: Filters, scope: Scope, client_id: str) -> List[Dict]:
    try:
        rpc_params = {
            "query_embedding": vector,
            "match_threshold": 0.45,
            "match_count": 5,
            "filter_client_id": client_id,
            "filter_speaker": filters.search_target_speaker if filters.search_target_speaker else None,
            "filter_session_numbers": None
        }
        
        if scope.mode == "specific_sessions" and scope.target_session_numbers:
             rpc_params["filter_session_numbers"] = scope.target_session_numbers

        response = supabase.rpc("search_utterances", rpc_params).execute()
        
        results = []
        for row in response.data:
            results.append({
                "text": row["utterance"],
                "session_id": row["session_id"],
                "session_number": row["session_number"],
                "sequence_number": row["sequence_number"],
                "speaker": row["speaker"],
                "start_seconds": row["start_seconds"],
                "score": row["similarity"]
            })
        return results

    except Exception as e:
        logger.error(f"[VECTOR SEARCH] RPC Failed: {e}")
        return []

async def _sql_hop(base_hits: List[Dict], offset: int) -> List[Dict]:
    if not base_hits: return []
    results = []
    for hit in base_hits[:2]: 
        try:
            target_seq = hit["sequence_number"] + offset
            res = supabase.table("utterances").select("*").eq("session_id", hit["session_id"]).eq("sequence_number", target_seq).maybe_single().execute()
            if res.data:
                row = res.data
                results.append({
                    "text": row["utterance"],
                    "speaker": row["speaker"],
                    "session_number": hit["session_number"],
                    "sequence_number": row["sequence_number"],
                    "start_seconds": row["start_seconds"],
                    "source_type": "hop_result"
                })
        except Exception: continue
    return results