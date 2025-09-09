# File: routes/mcp.py
# Directory: routes
# Purpose: Stable /mcp endpoints that orchestrate MCP (plan → context → dispatch via mcp_agent)
#          and return a normalized, JSON-safe envelope. Includes diagnostics and
#          bulletproof error handling so the UI never sees an opaque 500.

from __future__ import annotations

from typing import Optional, Literal, List, Dict, Any
from uuid import uuid4

from fastapi import APIRouter, Request, HTTPException, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
router = APIRouter(prefix="/mcp", tags=["mcp"])

# ── Logging shim (prefer core.logging) ───────────────────────────────────────
try:
    from core.logging import log_event  # type: ignore
except Exception:  # pragma: no cover
    import logging, json
    _LOG = logging.getLogger("relay.mcp")  # keep the 'relay.mcp' channel

    def log_event(event: str, data: Dict[str, Any] | None = None) -> None:
        """
        Fallback logger that mirrors core.logging.log_event signature.
        Writes a single-line, JSON-ish payload so corr_id is easy to grep.
        """
        payload = data or {}
        try:
            # Avoid raising if payload isn't JSON-serializable
            msg = json.dumps({"event": event, **payload}, default=str)
        except Exception:
            # Absolute safety net
            msg = f'{{"event": "{event}", "payload": "[unserializable]"}}'
        _LOG.info(msg)


# ── Orchestrator (async) ─────────────────────────────────────────────────────
# NOTE: mcp_agent internally decides which agent to use (e.g., echo_agent),
#       so routes/mcp.py doesn't import echo_agent directly.
from agents.mcp_agent import run_mcp  # must be async

router = APIRouter(prefix="/mcp", tags=["mcp"])

# ── Models ───────────────────────────────────────────────────────────────────
AllowedRole = Literal["planner", "echo", "docs", "codex", "control"]

class McpRunBody(BaseModel):
    query: str = Field(..., min_length=1, max_length=8000, description="User prompt to execute via MCP")
    role: Optional[AllowedRole] = Field(default="planner", description="Route hint; planner by default")
    files: Optional[List[str]] = Field(default=None, description="Optional file IDs/paths")
    topics: Optional[List[str]] = Field(default=None, description="Optional topics/tags")
    debug: bool = Field(default=False, description="Enable extra debug where supported")
    timeout_s: int = Field(default=45, ge=1, le=120, description="Soft timeout hint (agent may ignore)")

    @validator("query")
    def _strip_query(cls, v: str) -> str:
        s = (v or "").strip()
        if not s:
            raise ValueError("query must be non-empty")
        return s


class McpEnvelope(BaseModel):
    # Mirrors /ask envelope for UI consistency; `final_text` included for convenience.
    plan: Optional[Dict[str, Any]] = None
    routed_result: Optional[Dict[str, Any]] = None
    critics: Optional[List[Dict[str, Any]]] = None
    context: str = ""
    files_used: List[Dict[str, Any]] = []
    meta: Dict[str, Any] = {}
    final_text: str = ""


# ── Helpers ──────────────────────────────────────────────────────────────────
def _json_safe(obj: Any) -> Any:
    """Coerce arbitrary structures to JSON-safe values."""
    try:
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        if isinstance(obj, dict):
            return {str(k): _json_safe(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple, set)):
            return [_json_safe(x) for x in obj]
        return str(obj)
    except Exception:
        return "[unserializable]"


def _final_text_from(plan: Any, routed_result: Any) -> str:
    """Preferred extraction order: rr.response → rr.answer → plan.final_answer → ''."""
    if isinstance(routed_result, dict):
        txt = routed_result.get("response") or routed_result.get("answer") or ""
        if isinstance(txt, str) and txt.strip():
            return txt
        resp = routed_result.get("response")
        if isinstance(resp, dict):
            txt = resp.get("text") or ""
            if isinstance(txt, str) and txt.strip():
                return txt
    elif isinstance(routed_result, str) and routed_result.strip():
        return routed_result

    if isinstance(plan, dict):
        fa = plan.get("final_answer")
        if isinstance(fa, str) and fa.strip():
            return fa

    return ""


def _make_error(status: int, err: str, corr_id: str, hint: Optional[str] = None) -> JSONResponse:
    payload: Dict[str, Any] = {"error": err, "corr_id": corr_id}
    if hint:
        payload["hint"] = hint
    return JSONResponse(status_code=status, content=payload)


# ── Diagnostics ──────────────────────────────────────────────────────────────
@router.get("/ping")
async def mcp_ping() -> Dict[str, str]:
    # Include an impl signature so you can confirm you're on the new router.
    return {"status": "ok", "impl": "routes.mcp v2"}

@router.get("/diag")
async def mcp_diag() -> Dict[str, Any]:
    """Lightweight import/wiring check (no side effects)."""
    out = {"imports": {}, "checks": {}}
    try:
        import agents.mcp_agent as m  # existing orchestrator
        out["imports"]["mcp_agent"] = True
        out["checks"]["has_run_mcp"] = hasattr(m, "run_mcp")
    except Exception as e:
        out["imports"]["mcp_agent"] = f"ERR: {e}"

    try:
        import core.context_engine as ce
        out["imports"]["context_engine"] = True
        out["checks"]["ce_has_build_context"] = hasattr(ce, "build_context")
    except Exception as e:
        out["imports"]["context_engine"] = f"ERR: {e}"

    # NOTE: no relay_mcp import here by design (module does not exist in this repo)
    return out


# ── Main endpoint ────────────────────────────────────────────────────────────
@router.post("/run", response_model=McpEnvelope)
async def mcp_run(
    body: McpRunBody,
    request: Request,
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id"),
    x_corr_id: Optional[str] = Header(default=None, alias="X-Corr-Id"),
):
    """
    Execute the MCP pipeline (via mcp_agent) and return a normalized envelope.
    Never leaks raw exceptions. Frontend always gets JSON with a corr_id.
    """
    # Correlation ID: prefer X-Corr-Id → X-Request-Id → request.state.corr_id → new UUID
    corr_id = (
        (x_corr_id or "").strip()
        or (x_request_id or "").strip()
        or getattr(request.state, "corr_id", None)
        or uuid4().hex
    )

    log_event(
        "mcp_run_received",
        {
            "corr_id": corr_id,
            "role": (body.role or "planner"),
            "files_count": len(body.files or []),
            "topics_count": len(body.topics or []),
            "debug": body.debug,
        },
    )

    # Orchestrate
    try:
        result = await run_mcp(
            query=body.query,                 # already stripped by validator
            role=(body.role or "planner"),
            files=body.files or [],
            topics=body.topics or [],
            user_id="anonymous",
            debug=body.debug,
            corr_id=corr_id,
            # timeout_s=body.timeout_s,  # keep as future param if your agent supports it
        )
    except HTTPException:
        # Allow explicit HTTP exceptions to surface as-is (they already carry JSON)
        raise
    except Exception as e:
        log_event("mcp_run_exception", {"corr_id": corr_id, "error": str(e)})
        return _make_error(500, "mcp_failed", corr_id, hint="See server logs for mcp_run_exception")

    # Normalize & JSON-coerce the result
    if not isinstance(result, dict):
        result = {"routed_result": result}

    plan = result.get("plan") if isinstance(result.get("plan"), dict) else None
    rr = result.get("routed_result")
    critics = result.get("critics")
    context = result.get("context") or ""
    files_used = result.get("files_used") or []
    meta_in = result.get("meta") or {}

    final_text = _final_text_from(plan, rr)

    envelope = McpEnvelope(
        plan=_json_safe(plan) if plan else None,
        routed_result=_json_safe(rr) if isinstance(rr, (dict, str)) else {},
        critics=_json_safe(critics) if critics is not None else None,
        context=str(context or ""),
        files_used=_json_safe(files_used) if isinstance(files_used, list) else [],
        meta={**_json_safe(meta_in), "request_id": corr_id},
        final_text=final_text or "",
    )

    log_event(
        "mcp_run_completed",
        {
            "corr_id": corr_id,
            "route": envelope.meta.get("route"),
            "kb_hits": ((envelope.meta.get("kb") or {}).get("hits")),
            "kb_max_score": ((envelope.meta.get("kb") or {}).get("max_score")),
            "final_len": len(envelope.final_text or ""),
        },
    )

    return envelope
