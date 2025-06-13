# routes/ask.py
# Directory: routes/
# Purpose: API routes for user chat/ask endpoint with per-user memory, context pipeline, streaming, and audit logging.

import os
import logging
import datetime
from fastapi import APIRouter, Query, Request, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Optional, AsyncGenerator
from services.context_engine import ContextEngine
from services.agent import answer  # Should accept (user_id, question, context=None, stream=False)
from openai import OpenAIError

router = APIRouter(prefix="/ask", tags=["ask"])

def log_interaction(user_id, question, context, response):
    """Log user interaction for audit and future training."""
    ts = datetime.datetime.utcnow().isoformat()
    logline = f"{ts}\t{user_id}\tQ: {question}\tCTX: {len(context)} chars\tA: {str(response)[:80]}"
    logging.info(logline)
    # Optionally: append to file, DB, or Elastic

# === GET-based /ask endpoint ===
@router.get("")
async def ask_get(
    request: Request,
    question: str = Query(..., description="User query"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    debug: Optional[bool] = Query(False, description="Include context for debug")
):
    """
    Handle GET requests to /ask.
    Uses ContextEngine for max-relevant context.
    Optional debug param returns the context window.
    """
    user_id = x_user_id or "anonymous"
    try:
        print(f"[ask.py] Received GET question from {user_id}: {question}")
        ce = ContextEngine(user_id=user_id)
        context = ce.build_context(question)
        response = await answer(user_id, question, context=context)
        log_interaction(user_id, question, context, response)
        out = {"response": response}
        if debug:
            out["context"] = context
        return out
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# === POST-based /ask endpoint ===
@router.post("")
async def ask_post(
    request: Request,
    payload: dict,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    debug: Optional[bool] = Query(False, description="Include context for debug")
):
    """
    Handle POST requests to /ask.
    Uses ContextEngine for context.
    """
    user_id = x_user_id or "anonymous"
    question = payload.get("question", "")
    if not question:
        raise HTTPException(status_code=422, detail="Missing 'question' in request payload.")
    try:
        print(f"[ask.py] Received POST question from {user_id}: {question}")
        ce = ContextEngine(user_id=user_id)
        context = ce.build_context(question)
        response = await answer(user_id, question, context=context)
        log_interaction(user_id, question, context, response)
        out = {"response": response}
        if debug:
            out["context"] = context
        return out
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# === Streaming /ask endpoint (Optional, for LLM streaming agents) ===
@router.post("/stream")
async def ask_stream(
    request: Request,
    payload: dict,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id")
):
    """
    POST /ask/stream - Streams agent responses as they're generated.
    Requires agent.answer() to yield text chunks.
    """
    user_id = x_user_id or "anonymous"
    question = payload.get("question", "")
    if not question:
        raise HTTPException(status_code=422, detail="Missing 'question' in request payload.")
    try:
        ce = ContextEngine(user_id=user_id)
        context = ce.build_context(question)

        async def streamer() -> AsyncGenerator[str, None]:
            async for chunk in answer(user_id, question, context=context, stream=True):
                yield chunk

        # Optionally log start/end
        return StreamingResponse(streamer(), media_type="text/plain")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# === /test_openai route ===
@router.get("/test_openai")
async def test_openai():
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    try:
        print("[test_openai] Sending test request to OpenAI...")
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Ping test"}
            ]
        )
        return {"response": response.choices[0].message.content}
    except OpenAIError as e:
        print("❌ OpenAIError:", e)
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
