# File: ask.py
# Directory: routes
# Purpose: FastAPI endpoint for /ask — validates input, runs MCP pipeline, normalizes output,
#          and returns a stable response shape (with JSON-safe values).
#
# Upstream:
#   - ENV: (none specific; downstream agents/services may use their own env)
#   - Imports: fastapi, pydantic, typing, agents.mcp_agent.run_mcp, core.logging.log_event
#
# Downstream:
#   - agents.mcp_agent.run_mcp (planner → route dispatch → echo/critics)
#   - tests.test_ask_* (expected stable response shape)
#
# Contents:
#   - AskRequest (Pydantic)
#   - AskResponse (Pydantic)
#   - _json_safe(obj) helper
#   - _normalize_result(wrapper) helper
#   - POST /ask (ask)

from __future__ import annotations

import traceback
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, constr

from core.logging import log_event
from agents.mcp_agent import run_mcp

router = APIRouter()

# ---- Request / Response models ---------------------------------------------------------------

# imports — add Annotated, drop constr
from typing import Annotated
from pydantic import BaseModel, Field
# ...

class AskRequest(BaseModel):
    query: Annotated[str, Field(min_length=3, description="User question/prompt.")] = ...
    role: str | None = Field("planner", description="Planner (default) or a specific route key.")
    files: list[str] | None = Field(default=None, description="Optional file IDs/paths to include.")
    topics: list[str] | None = Field(default=None, description="Optional topical tags/labels.")
    user_id: str = Field("anonymous", description="Caller identity for logging/metrics.")
    debug: bool = Field(False, description="Enable extra debug output where supported.")

class AskResponse(BaseModel):
    """Normalized response from the MCP pipeline."""
    plan: Optional[Dict[str, Any]] = None
    routed_result: Dict[str, Any]
    critics: Optional[List[Dict[str, Any]]] = None
    context: str
    files_used: List[Dict[str, Any]] = []
    meta: Dict[str, Any] = {}


# ---- Helpers ---------------------------------------------------------------------------------

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


# ---- Route -----------------------------------------------------------------------------------

@router.post("/ask", response_model=AskResponse)
async def ask(payload: AskRequest):
    """
    Run the MCP pipeline for a validated query and return a normalized response.
    On internal failures, return structured 500 errors; planner/echo fallbacks preserve 200s upstream.
    """
    q = payload.query.strip()
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
        routed_result = _json_safe(normalized.get("routed_result", {}))
        critics = _json_safe(normalized.get("critics"))
        context = str(normalized.get("context") or "")
        files_used = _json_safe(normalized.get("files_used") or [])
    except Exception as e:
        log_event(
            "ask_normalize_exception",
            {"user": user_id, "error": str(e), "trace": traceback.format_exc()},
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "normalize_failed", "message": "Failed to normalize MCP result."},
        )

    log_event(
        "ask_completed",
        {
            "user": user_id,
            "role": role,
            "has_plan": bool(plan),
            "critics_len": None if critics is None else (len(critics) if isinstance(critics, list) else -1),
            "context_len": len(context),
            "routed_keys": list(routed_result.keys()) if isinstance(routed_result, dict) else str(type(routed_result)),
        },
    )

    return AskResponse(
        plan=plan,
        routed_result=routed_result,
        critics=critics if critics is not None else None,
        context=context,
        files_used=files_used if isinstance(files_used, list) else [],
        meta={"role": role, "debug": debug},
    )
