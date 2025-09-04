# File: routes/mcp.py
from __future__ import annotations
from typing import Optional, Literal, List, Dict, Any
from uuid import uuid4

from fastapi import APIRouter, Request, HTTPException, Header
from pydantic import BaseModel, Field

# Fallback-safe logging
try:
    from core.logging import log_event
except Exception:  # pragma: no cover
    def log_event(event: str, data: Dict[str, Any] | None = None) -> None:
        import logging
        logging.getLogger("relay.mcp").info("event=%s data=%s", event, (data or {}))

# Orchestrator
from agents.mcp_agent import run_mcp  # must be async

router = APIRouter(prefix="/mcp", tags=["mcp"])

AllowedRole = Literal["planner", "echo", "docs", "codex", "control"]

class McpRunBody(BaseModel):
    query: str = Field(..., min_length=1, max_length=8000)
    role: Optional[AllowedRole] = Field(default="planner")
    files: Optional[List[str]] = None
    topics: Optional[List[str]] = None
    debug: bool = False
    timeout_s: int = Field(default=45, ge=1, le=120)

@router.get("/ping")
async def mcp_ping() -> Dict[str, str]:
    return {"status": "ok"}

@router.post("/run")
async def mcp_run(
    body: McpRunBody,
    request: Request,
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-ID"),
):
    corr_id = x_request_id or getattr(request.state, "corr_id", None) or uuid4().hex
    log_event("mcp_run_received", {
        "corr_id": corr_id,
        "role": body.role,
        "files_count": len(body.files or []),
        "topics_count": len(body.topics or []),
        "debug": body.debug,
    })
    try:
        result = await run_mcp(
            query=body.query.strip(),
            role=(body.role or "planner").strip(),
            files=body.files or [],
            topics=body.topics or [],
            user_id="anonymous",
            debug=body.debug,
            corr_id=corr_id,
            timeout_s=body.timeout_s,
        )
    except Exception as e:
        log_event("mcp_run_exception", {"corr_id": corr_id, "error": str(e)})
        raise HTTPException(status_code=500, detail={"error": "mcp_failed", "corr_id": corr_id})

    # Ensure JSON-safe envelope with a final_text field
    if not isinstance(result, dict):
        result = {"routed_result": result}
    plan = result.get("plan") if isinstance(result.get("plan"), dict) else None
    rr = result.get("routed_result")
    final_text = ""
    if isinstance(rr, dict):
        final_text = (rr.get("response") or rr.get("answer") or "") or ""
    elif isinstance(rr, str):
        final_text = rr
    if not final_text and isinstance(plan, dict):
        final_text = plan.get("final_answer") or ""

    envelope = {
        "plan": plan,
        "routed_result": rr if isinstance(rr, (dict, str)) else {},
        "critics": result.get("critics"),
        "context": result.get("context") or "",
        "files_used": result.get("files_used") or [],
        "meta": {**(result.get("meta") or {}), "request_id": corr_id},
        "final_text": final_text or "",
    }
    log_event("mcp_run_completed", {"corr_id": corr_id, "final_len": len(envelope["final_text"])})
    return envelope
