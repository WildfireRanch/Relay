# File: ask.py
# Directory: routes
# Purpose: FastAPI endpoints for /ask — validates input, runs MCP pipeline, normalizes output,
#          provides GET compatibility and streaming shims, and guarantees JSON-safe responses.

from __future__ import annotations

import traceback
from typing import Any, Dict, List, Optional, Annotated, AsyncGenerator, Union

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.logging import log_event
from agents.mcp_agent import run_mcp

# Optional streaming agents
try:
    from agents.echo_agent import stream as echo_stream
except Exception:  # pragma: no cover
    echo_stream = None  # type: ignore

try:
    from agents.codex_agent import stream as codex_stream
except Exception:  # pragma: no cover
    codex_stream = None  # type: ignore

router = APIRouter()


# ── Request / Response models ────────────────────────────────────────────────

class AskRequest(BaseModel):
    """Validated payload for /ask (POST). Supports legacy 'question' alias."""
    model_config = {"populate_by_name": True}
    query: Annotated[str, Field(min_length=3, description="User question/prompt.", alias="question")] = ...
    role: Optional[str] = Field("planner", description="Planner (default) or a specific route key.")
    files: Optional[List[str]] = Field(default=None, description="Optional file IDs/paths to include.")
    topics: Optional[List[str]] = Field(default=None, description="Optional topical tags/labels.")
    user_id: str = Field("anonymous", description="Caller identity for logging/metrics.")
    debug: bool = Field(False, description="Enable extra debug output where supported.")


class AskResponse(BaseModel):
    """Normalized response from the MCP pipeline (UI should read final_text)."""
    plan: Optional[Dict[str, Any]] = None
    routed_result: Union[Dict[str, Any], str, None] = None
    critics: Optional[List[Dict[str, Any]]] = None
    context: str
    files_used: List[Dict[str, Any]] = []
    meta: Dict[str, Any] = {}
    # Canonical field for UI rendering:
    final_text: str = ""


class StreamRequest(BaseModel):
    """Payload for streaming endpoints; mirrors AskRequest but minimal."""
    model_config = {"populate_by_name": True}
    query: Annotated[str, Field(min_length=3, alias="question")] = ...
    context: Optional[str] = Field(default="", description="Optional prebuilt context")
    user_id: str = Field("anonymous")


# ── Helpers ─────────────────────────────────────────────────────────────────

def _json_safe(obj: Any) -> Any:
    """Best-effort coercion of arbitrary objects into JSON-serializable structures."""
    try:
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        if isinstance(obj, dict):
            return {str(k): _json_safe(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple, set)):
            return [_json_safe(x) for x in obj]
        # Fallback to string for exotic objects
        return str(obj)
    except Exception:
        return "[unserializable]"


def _normalize_result(result_or_wrapper: Dict[str, Any]) -> Dict[str, Any]:
    """
    Some callers may wrap results in {"result": {...}, "context": "..."}.
    Normalize into a single dict with the expected top-level keys.
    """
    if isinstance(result_or_wrapper, dict) and "result" in result_or_wrapper:
        inner = result_or_wrapper.get("result") or {}
        if isinstance(inner, dict):
            inner.setdefault("context", result_or_wrapper.get("context", ""))
            inner.setdefault("files_used", result_or_wrapper.get("files_used", []))
            return inner
    return result_or_wrapper


def _extract_final_text(plan: Any, routed_result: Any) -> str:
    """
    Canonical extraction of the user-facing text:
      1) routed_result.response
      2) routed_result.answer
      3) plan.final_answer
      4) "" (never None)
    """
    # routed_result may be dict/str/None
    if isinstance(routed_result, dict):
        text = routed_result.get("response") or routed_result.get("answer") or ""
        if isinstance(text, str) and text.strip():
            return text
    elif isinstance(routed_result, str) and routed_result.strip():
        return routed_result

    if isinstance(plan, dict):
        fa = plan.get("final_answer")
        if isinstance(fa, str) and fa.strip():
            return fa

    return ""


# ── Routes ──────────────────────────────────────────────────────────────────

@router.post("/ask", response_model=AskResponse)
async def ask(payload: AskRequest):
    """
    Run the MCP pipeline for a validated query and return a normalized response.
    On internal failures, return structured 500 errors; planner/echo fallbacks preserve 200s upstream.
    """
    q = (payload.query or "").strip()
    if not q:
        raise HTTPException(
            status_code=400,
            detail={"error": "bad_request", "hint": "query must be non-empty"},
        )

    role = (payload.role or "planner").strip() or "planner"
    files = payload.files or []
    topics = payload.topics or []
    user_id = payload.user_id
    debug = bool(payload.debug)

    log_event(
        "ask_received",
        {
            "user": user_id,
            "role": role,
            "files_count": len(files),
            "topics_count": len(topics),
            "debug": debug,
        },
    )

    # Run MCP
    try:
        mcp_raw = await run_mcp(
            query=q,
            role=role,
            files=files,
            topics=topics,
            user_id=user_id,
            debug=debug,
        )
    except Exception as e:
        log_event(
            "ask_mcp_exception",
            {"user": user_id, "error": str(e), "trace": traceback.format_exc()},
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "mcp_failed", "message": "Failed to run MCP."},
        )

    # Normalize & JSON-coerce all parts
    try:
        normalized = _normalize_result(mcp_raw)
        plan = _json_safe(normalized.get("plan"))
        routed_result = normalized.get("routed_result", {})
        critics = _json_safe(normalized.get("critics"))
        context = str(normalized.get("context") or "")
        files_used = _json_safe(normalized.get("files_used") or [])
        upstream_meta = normalized.get("meta") or {}
        # Final text for UI
        final_text = _extract_final_text(plan, routed_result)
    except Exception as e:
        log_event(
            "ask_normalize_exception",
            {"user": user_id, "error": str(e), "trace": traceback.format_exc()},
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "normalize_failed", "message": "Failed to normalize MCP result."},
        )

    # Ensure routed_result is JSON-safe (after final_text extraction to avoid losing non-serializable fields prematurely)
    routed_result_safe = _json_safe(routed_result)

    # Merge meta/provenance coming from MCP
    meta: Dict[str, Any] = {"role": role, "debug": debug}
    if isinstance(upstream_meta, dict):
        # upstream meta may include origin, antiparrot, timings_ms, request_id, etc.
        meta.update(_json_safe(upstream_meta))

    # Quick ops summary for parity with UI
    log_event(
        "ask_response_summary",
        {
            "user": user_id,
            "origin": meta.get("origin"),
            "final_text_head": (final_text or "")[:200],
        },
    )

    return AskResponse(
        plan=plan if isinstance(plan, dict) else None,
        routed_result=routed_result_safe if isinstance(routed_result_safe, (dict, str)) else {},
        critics=critics if critics is not None else None,
        context=context,
        files_used=files_used if isinstance(files_used, list) else [],
        meta=meta,
        final_text=final_text,
    )


@router.get("/ask")
async def ask_get(question: Annotated[str, Query(min_length=3)]):
    """
    Legacy GET shim: /ask?question=...
    Reuses POST logic by constructing an AskRequest, so behavior stays identical.
    """
    payload = AskRequest.model_validate({"question": question})
    return await ask(payload)


@router.post("/ask/stream")
async def ask_stream(payload: StreamRequest):
    """
    Streamed answer via Echo. Returns 501 if echo streaming is unavailable.
    """
    if echo_stream is None:
        raise HTTPException(status_code=501, detail={"error": "not_implemented", "message": "Echo streaming not available."})

    q = (payload.query or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail={"error": "bad_request", "hint": "query must be non-empty"})

    async def gen() -> AsyncGenerator[bytes, None]:
        try:
            async for chunk in echo_stream(query=q, context=payload.context or "", user_id=payload.user_id):
                yield chunk.encode("utf-8")
        except Exception as e:
            log_event("ask_stream_error", {"error": str(e)})
            yield f"[stream error] {str(e)}".encode("utf-8")

    return StreamingResponse(gen(), media_type="text/plain")


@router.post("/ask/codex_stream")
async def ask_codex_stream(payload: StreamRequest):
    """
    Streamed code/patch output via Codex agent. Returns 501 if codex streaming is unavailable.
    """
    if codex_stream is None:
        raise HTTPException(status_code=501, detail={"error": "not_implemented", "message": "Codex streaming not available."})

    q = (payload.query or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail={"error": "bad_request", "hint": "query must be non-empty"})

    async def gen() -> AsyncGenerator[bytes, None]:
        try:
            async for chunk in codex_stream(query=q, context=payload.context or "", user_id=payload.user_id):
                yield chunk.encode("utf-8")
        except Exception as e:
            log_event("ask_codex_stream_error", {"error": str(e)})
            yield f"[stream error] {str(e)}".encode("utf-8")

    return StreamingResponse(gen(), media_type="text/plain")
    from core.logging import log_event

from core.logging import log_event

log_event("reply_summary", {
  "route": (result.get("meta") or {}).get("route"),
  "origin": (result.get("meta") or {}).get("origin"),
  "plan_id": (result.get("meta") or {}).get("plan_id"),
  "final_len": len(result.get("final_text") or ""),
  "rr_has_answer": bool((result.get("routed_result") or {}).get("answer")),
})



