# ──────────────────────────────────────────────────────────────────────────────
# File: routes/ask.py
# Purpose: Frontdoor for Echo/Codex/MCP — non-streaming & streaming endpoints
#          with consistent UI response shape and robust error handling.
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
from typing import Optional, List, Dict, Any, AsyncIterator

from fastapi import APIRouter, Query, Request, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, validator

from agents.mcp_agent import run_mcp
from agents.codex_agent import stream as codex_stream
from agents.echo_agent import stream as echo_stream
from utils.openai_client import create_openai_client
from openai import OpenAIError

router = APIRouter(prefix="/ask", tags=["ask"])

# ── Logging setup (respect global LOG_LEVEL); do not log secrets or long texts
log = logging.getLogger("ask")

# ──────────────────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────────────────

class AskGetResponse(BaseModel):
    """Stable UI-friendly response."""
    answer: str = Field(..., description="Primary textual answer for the UI")
    debug_payload: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional raw payload if debug=true"
    )

class AskPostPayload(BaseModel):
    question: str = Field(..., min_length=1)
    context: Optional[str] = ""  # short, UI context or system hints
    files: Optional[List[str]] = Field(default_factory=list)
    topics: Optional[List[str]] = Field(default_factory=list)
    role: Optional[str] = Field(default="planner")

    @validator("files", "topics", pre=True)
    def _default_to_list(cls, v):
        if v is None:
            return []
        return v

class AskStreamPayload(BaseModel):
    question: str = Field(..., min_length=1)
    context: Optional[str] = ""
    files: Optional[List[str]] = Field(default_factory=list)
    topics: Optional[List[str]] = Field(default_factory=list)
    role: Optional[str] = Field(default="planner")

# ──────────────────────────────────────────────────────────────────────────────
# Agent routing (streaming)
# ──────────────────────────────────────────────────────────────────────────────

STREAM_ROUTING_TABLE = {
    "codex": codex_stream,
    "echo": echo_stream,
    # add more streaming agents here as needed
}

def _pick_stream_fn(role: str) -> Any:
    """Return a streaming fn; default to echo."""
    return STREAM_ROUTING_TABLE.get(role, echo_stream)

def _normalize_answer(mcp_result: Dict[str, Any]) -> str:
    """
    Normalize heterogeneous MCP outputs to a single answer string
    for the frontend. Tries common keys in order.
    """
    if not isinstance(mcp_result, dict):
        return str(mcp_result)
    for key in ("answer", "response", "final", "text", "message"):
        val = mcp_result.get(key)
        if isinstance(val, str) and val.strip():
            return val
    # fallback: best effort stringify
    return str(mcp_result)[:5000]  # cap to avoid huge payloads in UI

# ──────────────────────────────────────────────────────────────────────────────
# GET /ask — quick dev/test; normalized output; optional debug echo-through
# ──────────────────────────────────────────────────────────────────────────────

@router.get("", response_model=AskGetResponse)
async def ask_get(
    request: Request,
    question: str = Query(..., description="User question"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    debug: Optional[bool] = Query(False, description="If true, include raw MCP payload"),
    role: Optional[str] = Query("planner", description="Agent role: planner|echo|codex|..."),
    files: Optional[str] = Query(None, description="CSV of files for context"),
    topics: Optional[str] = Query(None, description="CSV of topics for context"),
):
    user_id = x_user_id or "anonymous"
    file_list = [f.strip() for f in files.split(",")] if files else []
    topic_list = [t.strip() for t in topics.split(",")] if topics else []

    if not question:
        raise HTTPException(status_code=422, detail="Missing 'question' parameter.")

    try:
        log.info("ASK[GET] user=%s role=%s qlen=%d files=%d topics=%d debug=%s",
                 user_id, role, len(question), len(file_list), len(topic_list), bool(debug))

        mcp_result = await run_mcp(
            query=question,
            files=file_list,
            topics=topic_list,
            role=role,
            user_id=user_id,
            debug=bool(debug),
        )
        answer = _normalize_answer(mcp_result)
        return AskGetResponse(answer=answer, debug_payload=mcp_result if debug else None)

    except HTTPException:
        raise
    except Exception as e:
        log.exception("ASK[GET] error user=%s role=%s", user_id, role)
        raise HTTPException(status_code=500, detail="Ask failed")

# ──────────────────────────────────────────────────────────────────────────────
# POST /ask — main entry; normalized output; optional debug echo-through
# ──────────────────────────────────────────────────────────────────────────────

@router.post("", response_model=AskGetResponse)
async def ask_post(
    request: Request,
    payload: AskPostPayload,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    debug: Optional[bool] = Query(False),
):
    user_id = x_user_id or "anonymous"
    if not payload.question:
        raise HTTPException(status_code=422, detail="Missing 'question' in request payload.")

    try:
        log.info("ASK[POST] user=%s role=%s qlen=%d files=%d topics=%d debug=%s",
                 user_id, payload.role, len(payload.question),
                 len(payload.files or []), len(payload.topics or []), bool(debug))

        mcp_result = await run_mcp(
            query=payload.question,
            files=payload.files,
            topics=payload.topics,
            role=payload.role or "planner",
            user_id=user_id,
            debug=bool(debug),
        )
        answer = _normalize_answer(mcp_result)
        return AskGetResponse(answer=answer, debug_payload=mcp_result if debug else None)

    except HTTPException:
        raise
    except Exception as e:
        log.exception("ASK[POST] error user=%s role=%s", user_id, payload.role)
        raise HTTPException(status_code=500, detail="Ask failed")

# ──────────────────────────────────────────────────────────────────────────────
# POST /ask/stream — streaming via routed agent (fallback to echo)
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/stream")
async def ask_stream(
    request: Request,
    payload: AskStreamPayload,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
):
    user_id = x_user_id or "anonymous"
    if not payload.question:
        raise HTTPException(status_code=422, detail="Missing 'question' in request payload.")

    try:
        # Plan + route to discover best streaming agent
        mcp_result = await run_mcp(
            query=payload.question,
            files=payload.files,
            topics=payload.topics,
            role=payload.role or "planner",
            user_id=user_id,
            debug=False,
        )
        plan = mcp_result.get("plan", {}) if isinstance(mcp_result, dict) else {}
        used_route = plan.get("meta_override") or plan.get("route") or (payload.role or "echo")

        stream_fn = _pick_stream_fn(str(used_route))
        log.info("ASK[STREAM] user=%s route=%s qlen=%d", user_id, used_route, len(payload.question))

        # Agents' stream fns are async generators yielding text chunks
        async def _generator() -> AsyncIterator[bytes]:
            try:
                async for chunk in stream_fn(payload.question, payload.context or "", user_id):
                    # ensure bytes
                    yield (chunk if isinstance(chunk, (bytes, bytearray)) else str(chunk)).encode("utf-8", "ignore")
            except Exception:
                log.exception("ASK[STREAM] streaming failed user=%s route=%s", user_id, used_route)
                # terminate stream with a short hint
                yield b"\n\n[stream terminated]\n"

        return StreamingResponse(_generator(), media_type="text/plain")

    except HTTPException:
        raise
    except Exception:
        log.exception("ASK[STREAM] error user=%s", user_id)
        raise HTTPException(status_code=500, detail="Stream failed")

# ──────────────────────────────────────────────────────────────────────────────
# POST /ask/codex_stream — direct code streaming (expects context)
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/codex_stream")
async def ask_codex_stream(
    request: Request,
    payload: AskStreamPayload,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
):
    user_id = x_user_id or "anonymous"
    if not payload.question or not (payload.context or "").strip():
        raise HTTPException(status_code=422, detail="Missing 'question' or 'context' in request.")
    try:
        return StreamingResponse(
            codex_stream(payload.question, payload.context or "", user_id),
            media_type="text/plain",
        )
    except Exception:
        log.exception("ASK[CODEX_STREAM] error user=%s", user_id)
        raise HTTPException(status_code=500, detail="Codex stream failed")

# ──────────────────────────────────────────────────────────────────────────────
# POST /ask/echo_stream — direct echo streaming
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/echo_stream")
async def ask_echo_stream(
    request: Request,
    payload: AskStreamPayload,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
):
    user_id = x_user_id or "anonymous"
    if not payload.question:
        raise HTTPException(status_code=422, detail="Missing 'question' in request.")
    try:
        return StreamingResponse(
            echo_stream(payload.question, payload.context or "", user_id),
            media_type="text/plain",
        )
    except Exception:
        log.exception("ASK[ECHO_STREAM] error user=%s", user_id)
        raise HTTPException(status_code=500, detail="Echo stream failed")

# ──────────────────────────────────────────────────────────────────────────────
# GET /ask/test_openai — connectivity probe
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/test_openai")
async def test_openai() -> Dict[str, str]:
    """
    Connectivity probe for OpenAI. Returns a short response if the key/model is valid.
    """
    try:
        client = create_openai_client()
        # If your client is async, this await is correct. If it's sync, drop 'await'.
        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Ping test"},
            ],
            max_tokens=16,
        )
        text = (resp.choices[0].message.content or "").strip()
        return {"response": text or "ok"}
    except OpenAIError as e:
        # Upstream model/network error → 502
        log.warning("ASK[OPENAI_PROBE] OpenAIError: %s", e)
        raise HTTPException(status_code=502, detail="OpenAI upstream error")
    except Exception as e:
        log.exception("ASK[OPENAI_PROBE] unexpected error")
        raise HTTPException(status_code=500, detail="OpenAI probe failed")
