# ──────────────────────────────────────────────────────────────────────────────
# File: routes/ask.py
# Purpose: API routes for /ask endpoints — user entry point to Relay agents
# Delegates logic to planner_agent
# ──────────────────────────────────────────────────────────────────────────────

import os, traceback
from fastapi import APIRouter, Query, Request, Header, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional
from agents.codex_agent import handle as codex_agent
from agents import planner_agent
from openai import AsyncOpenAI, OpenAIError
from utils.openai_client import create_openai_client
from fastapi.responses import StreamingResponse
from agents.codex_agent import stream as codex_stream


router = APIRouter(prefix="/ask", tags=["ask"])

# === GET /ask ==================================================================
@router.get("")
async def ask_get(
    request: Request,
    question: str = Query(...),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    debug: Optional[bool] = Query(False),
    reflect: Optional[bool] = Query(False),
    score_threshold: Optional[float] = Query(None)
):
    user_id = x_user_id or "anonymous"
    try:
        return await planner_agent.handle_query(
            user_id=user_id,
            query=question,
            reflect=reflect,
            debug=debug,
            score_threshold=score_threshold
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# === POST /ask =================================================================
@router.post("")
async def ask_post(
    request: Request,
    payload: dict,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    debug: Optional[bool] = Query(False),
    reflect: Optional[bool] = Query(False),
    score_threshold: Optional[float] = Query(None)
):
    user_id = x_user_id or "anonymous"
    question = payload.get("question", "")
    context = payload.get("context", "")
    
    if not question:
        raise HTTPException(status_code=422, detail="Missing 'question' in request payload.")

    try:
        # Check if this looks like a Codex-style edit prompt
        codex_keywords = ("fix", "refactor", "add docstring", "make this async", "convert to class", "clean up")
        if context and any(kw in question.lower() for kw in codex_keywords):
          return await codex_agent(question, context, user_id) 


        # Default planner agent
        return await planner_agent.handle_query(
            user_id=user_id,
            query=question,
            reflect=reflect,
            debug=debug,
            score_threshold=score_threshold,
            payload=payload
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# === POST /ask/stream ==========================================================
@router.post("/stream")
async def ask_stream(
    request: Request,
    payload: dict,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    reflect: Optional[bool] = Query(False)
):
    user_id = x_user_id or "anonymous"
    question = payload.get("question", "")
    if not question:
        raise HTTPException(status_code=422, detail="Missing 'question' in request payload.")
    try:
        return await planner_agent.handle_stream(user_id, question, reflect=reflect)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# === POST /ask/codex_stream ===================================================
@router.post("/codex_stream")
async def ask_codex_stream(
    request: Request,
    payload: dict,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id")
):
    user_id = x_user_id or "anonymous"
    question = payload.get("question", "")
    context = payload.get("context", "")

    if not question or not context:
        raise HTTPException(status_code=422, detail="Missing 'question' or 'context' in request.")

    return StreamingResponse(codex_stream(question, context, user_id), media_type="text/plain")



# === GET /ask/test_openai ======================================================
@router.get("/test_openai")
async def test_openai():
    try:
        client = create_openai_client()
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Ping test"}
            ]
        )
        return { "response": response.choices[0].message.content }
    except OpenAIError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
