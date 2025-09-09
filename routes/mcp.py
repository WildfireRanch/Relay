# File: routes/mcp.py
# Purpose: Stable /mcp endpoints; import mcp_agent lazily inside handlers to avoid circular imports.

from __future__ import annotations

from typing import Optional, Literal, List, Dict, Any
from uuid import uuid4

from fastapi import APIRouter, Request, HTTPException, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

# Structured logging shim
try:
    from core.logging import log_event
except Exception:  # pragma: no cover
    import logging, json
    _LOG = logging.getLogger("relay.mcp")
    def log_event(event: str, data: Dict[str, Any] | None = None) -> None:
        payload = {"event": event, **(data or {})}
        try:
            _LOG.info(json.dumps(payload, default=str))
        except Exception:
            _LOG.info("event=%s data=%s", event, (data or {}))

router = APIRouter(prefix="/mcp", tags=["mcp"])

AllowedRole = Literal["planner", "echo", "docs", "codex", "control"]

class McpRunBody(BaseModel):
    query: str = Field(..., min_length=1, max_length=8000)
    role: Optional[AllowedRole] = Field(default="planner")
    files: Optional[List[str]] = None
    topics: Optional[List[str]] = None
    debug: bool = False
    timeout_s: int = Field(default=45, ge=1, le=120)

    @validator("query")
    def _strip_query(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("query must be non-empty")
        return v

class McpEnvelope(BaseModel):
    plan: Optional[Dict[str, Any]] = None
    routed_result: Optional[Dict[str, Any] | str] = None
    critics: Optional[List[Dict[str, Any]]] = None
    context: str = ""
    files_used: List[Dict[str, Any]] = []
    meta: Dict[str, Any] = {}
    final_text: str = ""

def _json_safe(obj: Any) -> Any:
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

def _final_text_from(plan: Any, rr: Any) -> str:
    if isinstance(rr, dict):
        txt = rr.get("response") or rr.get("answer") or ""
        if isinstance(txt, str) and txt.strip():
            return txt
        resp = rr.get("response")
        if isinstance(resp, dict):
            t = resp.get("text") or ""
            if isinstance(t, str) and t.strip():
                return t
    elif isinstance(rr, str) and rr.strip():
        return rr
    if isinstance(plan, dict):
        fa = plan.get("final_answer")
        if isinstance(fa, str) and fa.strip():
            return fa
    return ""

def _err(status: int, err: str, corr_id: str, hint: Optional[str] = None) -> JSONResponse:
    payload: Dict[str, Any] = {"error": err, "corr_id": corr_id}
    if hint:
        payload["hint"] = hint
    return JSONResponse(status_code=status, content=payload)

@router.get("/ping")
async def mcp_ping() -> Dict[str, str]:
    return {"status": "ok", "impl": "routes.mcp v2 (lazy import)"}

@router.post("/run", response_model=McpEnvelope)
async def mcp_run(
    body: McpRunBody,
    request: Request,
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id"),
    x_corr_id: Optional[str] = Header(default=None, alias="X-Corr-Id"),
):
    """
    Execute MCP via agents.mcp_agent.run_mcp. Import is deferred to avoid circular imports.
    """
    # Defer the import here (prevents circular import during module init)
    try:
        from agents.mcp_agent import run_mcp  # type: ignore
    except Exception as e:
        cid = x_corr_id or x_request_id or getattr(request.state, "corr_id", None) or uuid4().hex
        log_event("mcp_import_error", {"corr_id": cid, "error": str(e)})
        return _err(500, "mcp_failed", cid, hint="Import run_mcp failed; see mcp_import_error")

    corr_id = (
        (x_corr_id or "").strip()
        or (x_request_id or "").strip()
        or getattr(request.state, "corr_id", None)
        or uuid4().hex
    )

    log_event("mcp_run_received", {
        "corr_id": corr_id,
        "role": (body.role or "planner"),
        "files_count": len(body.files or []),
        "topics_count": len(body.topics or []),
        "debug": body.debug,
    })

    try:
        result = await run_mcp(
            query=body.query,
            role=(body.role or "planner"),
            files=body.files or [],
            topics=body.topics or [],
            user_id="anonymous",
            debug=body.debug,
            corr_id=corr_id,
            # timeout_s=body.timeout_s,  # keep as future hint
        )
    except HTTPException:
        raise
    except Exception as e:
        log_event("mcp_run_exception", {"corr_id": corr_id, "error": str(e)})
        return _err(500, "mcp_failed", corr_id, hint="See server logs for mcp_run_exception")

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

    log_event("mcp_run_completed", {
        "corr_id": corr_id,
        "route": envelope.meta.get("route"),
        "kb_hits": ((envelope.meta.get("kb") or {}).get("hits")),
        "kb_max_score": ((envelope.meta.get("kb") or {}).get("max_score")),
        "final_len": len(envelope.final_text or ""),
    })

    return envelope
