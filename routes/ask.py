# ──────────────────────────────────────────────────────────────────────────────
# File: routes/ask.py
# Purpose:
#   FastAPI endpoint for Relay "Ask Echo":
#     - Validates input (query, role, files, topics, debug)
#     - Calls MCP (planner or explicit role)
#     - Normalizes outputs (consistent JSON)
#     - Adds high-signal logs and actionable errors
#
# Behavior:
#   - Always returns 200 on success with:
#       { plan?, routed_result, critics?, context, files_used, meta }
#   - Returns 400 for bad input, 500 for internal failures (with detail.hint)
#
# Notes:
#   - Works whether run_mcp returns top-level result or {"result": ...}
#   - Prevents non-serializable data from escaping
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
import traceback
from typing import List, Optional, Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, validator

from core.logging import log_event
from agents.mcp_agent import run_mcp

router = APIRouter()
log = logging.getLogger("ask_route")


# ─── Pydantic Models ─────────────────────────────────────────────────────────

class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User query")
    role: str = Field("planner", description="Target agent role or 'planner'")
    files: Optional[List[str]] = Field(default=None)
    topics: Optional[List[str]] = Field(default=None)
    user_id: str = Field("anonymous")
    debug: bool = Field(False)

    @validator("role")
    def _role_ok(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            return "planner"
        return v


class AskResponse(BaseModel):
    plan: Optional[Dict[str, Any]] = None
    routed_result: Dict[str, Any]
    critics: Optional[List[Dict[str, Any]]] = None
    context: str
    files_used: List[Dict[str, Any]] = []
    meta: Dict[str, Any] = {}


# ─── Helpers ────────────────────────────────────────────────────────────────

def _json_safe(obj: Any) -> Any:
    """Defensive JSON sanitizer for logs and responses."""
    try:
        # Fast path for already-JSONable things
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        if isinstance(obj, dict):
            return {str(k): _json_safe(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple, set)):
            return [_json_safe(x) for x in obj]
        # Fallback to str()
        return str(obj)
    except Exception:
        return f"[unserializable:{type(obj).__name__}]"


def _normalize_result(result_or_wrapper: Dict[str, Any]) -> Dict[str, Any]:
    """
    run_mcp may return either:
      A) {"plan":..., "routed_result":..., "critics":..., "context":..., "files_used":[...]}
      B) {"result": { ...same as A... }, "context": "...", "files_used":[...]} (debug path)
    Normalize to shape A.
    """
    if "result" in result_or_wrapper and isinstance(result_or_wrapper["result"], dict):
        inner = result_or_wrapper["result"]
        # Prefer the inner context/files_used if present; otherwise fall back.
        inner.setdefault("context", result_or_wrapper.get("context", ""))
        inner.setdefault("files_used", result_or_wrapper.get("files_used", []))
        return inner
    return result_or_wrapper


# ─── Routes ─────────────────────────────────────────────────────────────────

@router.post("/ask", response_model=AskResponse)
async def ask(payload: AskRequest):
    # 1) Validate early and log the request (without sensitive data)
    q = payload.query.strip()
    if not q:
        raise HTTPException(status_code=400, detail={"error": "bad_request", "hint": "query must be non-empty"})

    role = payload.role
    files = payload.files or []
    topics = payload.topics or []
    user_id = payload.user_id
    debug = bool(payload.debug)

    log_event("ask_received", {
        "user": user_id,
        "role": role,
        "files_count": len(files),
        "topics_count": len(topics),
        "debug": debug,
        "q_len": len(q),
    })

    # 2) Call MCP
    try:
        mcp_raw = await run_mcp(
            query=q,
            files=files,
            topics=topics,
            role=role,
            user_id=user_id,
            debug=debug,
        )
    except Exception as e:
        log_event("ask_mcp_exception", {"user": user_id, "role": role, "error": str(e), "trace": traceback.format_exc()})
        raise HTTPException(
            status_code=500,
            detail={
                "error": "mcp_failed",
                "message": "MCP orchestration failed",
                "hint": "Check planner/route logs; enable debug to see sections",
            },
        )

    # 3) Normalize shape and make it JSON-safe
    try:
        normalized = _normalize_result(mcp_raw)
        plan = _json_safe(normalized.get("plan"))
        routed_result = _json_safe(normalized.get("routed_result", {}))
        critics = _json_safe(normalized.get("critics"))
        context = str(normalized.get("context") or "")
        files_used = _json_safe(normalized.get("files_used") or [])
    except Exception as e:
        log_event("ask_normalize_exception", {"user": user_id, "error": str(e), "trace": traceback.format_exc()})
        raise HTTPException(
            status_code=500,
            detail={"error": "normalize_failed", "message": "Failed to normalize MCP result"},
        )

    # 4) Final telemetry
    log_event("ask_completed", {
        "user": user_id,
        "role": role,
        "has_plan": bool(plan),
        "critics": None if critics is None else len(critics),
        "context_len": len(context),
        "routed_keys": list(routed_result.keys()) if isinstance(routed_result, dict) else type(routed_result).__name__,
    })

    # 5) Response
    return AskResponse(
        plan=plan,
        routed_result=routed_result,
        critics=critics,
        context=context,
        files_used=files_used,
        meta={"role": role, "debug": debug},
    )
