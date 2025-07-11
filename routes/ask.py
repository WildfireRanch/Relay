# ──────────────────────────────────────────────────────────────────────────────
# File: ask.py
# Directory: routes
# Purpose: # Purpose: Provides API endpoints for handling various types of requests and interactions with OpenAI models and agents.
#
# Upstream:
#   - ENV: —
#   - Imports: agents.codex_agent, agents.echo_agent, agents.mcp_agent, fastapi, fastapi.responses, openai, traceback, typing, utils.openai_client
#
# Downstream:
#   - main
#
# Contents:
#   - ask_codex_stream()
#   - ask_echo_stream()
#   - ask_get()
#   - ask_post()
#   - ask_stream()
#   - test_openai()

# ──────────────────────────────────────────────────────────────────────────────

import traceback
from fastapi import APIRouter, Query, Request, Header, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional

from agents.mcp_agent import run_mcp
from agents.codex_agent import stream as codex_stream
from agents.echo_agent import stream as echo_stream
from utils.openai_client import create_openai_client
from openai import OpenAIError

router = APIRouter(prefix="/ask", tags=["ask"])

# Streaming map for roles that support it
STREAM_ROUTING_TABLE = {
    "codex": codex_stream,
    "echo": echo_stream,
    # Add more streaming agents here as needed in the future
}

# === GET /ask ==================================================================
@router.get("")
async def ask_get(
    request: Request,
    question: str = Query(..., description="User's natural language question"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    debug: Optional[bool] = Query(False, description="Return debug/context info"),
    role: Optional[str] = Query("planner", description="Which agent role to use (planner, echo, codex, etc)"),
    files: Optional[str] = Query(None, description="Comma-separated file list for context"),
    topics: Optional[str] = Query(None, description="Comma-separated topics for context")
):
    """
    GET version of /ask, mostly for quick dev/testing.
    Routes to MCP with appropriate agent role.
    Echo is always available as both primary and fallback agent.
    """
    user_id = x_user_id or "anonymous"
    file_list = [f.strip() for f in files.split(",")] if files else []
    topic_list = [t.strip() for t in topics.split(",")] if topics else []

    if not question:
        raise HTTPException(status_code=422, detail="Missing 'question' parameter.")

    try:
        return await run_mcp(
            query=question,
            files=file_list,
            topics=topic_list,
            role=role,
            user_id=user_id,
            debug=debug
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
):
    """
    Main POST endpoint for /ask — entrypoint for planner, codex, echo, or other agents.
    Routes all queries to MCP for context injection, agent routing, and critics.
    Echo is always available as both primary and fallback agent.
    """
    user_id = x_user_id or "anonymous"
    question = payload.get("question", "")
    context = payload.get("context", "")
    files = payload.get("files", [])
    topics = payload.get("topics", [])
    role = payload.get("role", "planner")

    if not question:
        raise HTTPException(status_code=422, detail="Missing 'question' in request payload.")

    try:
        result = await run_mcp(
            query=question,
            files=files,
            topics=topics,
            role=role,
            user_id=user_id,
            debug=debug
        )
        return result
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# === POST /ask/stream ==========================================================
@router.post("/stream")
async def ask_stream(
    request: Request,
    payload: dict,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
):
    """
    Streaming endpoint for planner/meta/explicit agent roles via MCP routing.
    If the routed agent supports streaming, streams the response.
    Fallbacks to Echo stream if the routed agent doesn't support streaming.
    """
    user_id = x_user_id or "anonymous"
    question = payload.get("question", "")
    context = payload.get("context", "")
    files = payload.get("files", [])
    topics = payload.get("topics", [])
    role = payload.get("role", "planner")

    if not question:
        raise HTTPException(status_code=422, detail="Missing 'question' in request payload.")

    try:
        # Get plan and route via MCP (to know the agent/role to stream)
        mcp_result = await run_mcp(
            query=question,
            files=files,
            topics=topics,
            role=role,
            user_id=user_id,
            debug=False
        )
        plan = mcp_result.get("plan", {})
        used_route = plan.get("meta_override") or plan.get("route") or role

        stream_fn = STREAM_ROUTING_TABLE.get(used_route, echo_stream)
        return StreamingResponse(
            stream_fn(question, context, user_id),
            media_type="text/plain"
        )
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
    """
    Streaming endpoint for Codex/code edits. Streams text output directly.
    """
    user_id = x_user_id or "anonymous"
    question = payload.get("question", "")
    context = payload.get("context", "")

    if not question or not context:
        raise HTTPException(status_code=422, detail="Missing 'question' or 'context' in request.")

    try:
        return StreamingResponse(codex_stream(question, context, user_id), media_type="text/plain")
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# === POST /ask/echo_stream ====================================================
@router.post("/echo_stream")
async def ask_echo_stream(
    request: Request,
    payload: dict,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
):
    """
    Streaming endpoint for Echo (LLM chat) responses.
    """
    user_id = x_user_id or "anonymous"
    question = payload.get("question", "")
    context = payload.get("context", "")

    if not question:
        raise HTTPException(status_code=422, detail="Missing 'question' in request.")

    try:
        return StreamingResponse(
            echo_stream(question, context, user_id),
            media_type="text/plain"
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# === GET /ask/test_openai ======================================================
@router.get("/test_openai")
async def test_openai():
    """
    Quick endpoint to verify OpenAI API connectivity and model health.
    """
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
