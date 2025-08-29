# ──────────────────────────────────────────────────────────────────────────────
# File: routes/mcp.py
# Directory: routes/
# Purpose: API route for direct access to MCP handler (run_mcp) for testing,
#          automation, or admin use. Backward-compatible with {query|question|prompt}.
#
# Upstream:
#   - ENV: —
#   - Imports: agents.mcp_agent.run_mcp, fastapi, pydantic, typing
#
# Downstream:
#   - main (include_router)
#
# Contents:
#   - MCPRunRequest (Pydantic)
#   - MCPRunResponse (typing alias; passthrough)
#   - mcp_run()
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

from typing import Any, Dict, List, Optional, Annotated

from fastapi import APIRouter, HTTPException, Request, Header
from pydantic import BaseModel, Field

from core.logging import log_event
from agents.mcp_agent import run_mcp

router = APIRouter(prefix="/mcp", tags=["mcp"])


# ---- Models ------------------------------------------------------------------

class MCPRunRequest(BaseModel):
    """
    Flexible payload: accepts `query` (preferred) or legacy `question` / `prompt`.
    """
    model_config = {"populate_by_name": True}
    query: Annotated[str, Field(min_length=1, alias="question")] = Field(
        ..., description="User prompt. Alias: 'question' or 'prompt' via shim."
    )
    # For extra compatibility with 'prompt', allow it to be passed and map it in mcp_run.
    prompt: Optional[str] = Field(default=None, description="Legacy alias for 'query' (optional).")

    files: Optional[List[str]] = Field(default=None, description="Optional file IDs/paths.")
    topics: Optional[List[str]] = Field(default=None, description="Optional topic tags.")
    role: str = Field(default="planner", description="Planner (default) or a specific route key.")
    user_id: Optional[str] = Field(default=None, description="Logical user id; header X-User-Id overrides when set.")
    debug: bool = Field(default=False, description="Enable diagnostic paths where supported.")


MCPRunResponse = Dict[str, Any]  # passthrough shape from agents.mcp_agent.run_mcp


# ---- Route -------------------------------------------------------------------

@router.post("/run")
async def mcp_run(
    request: Request,
    x_user_id: Annotated[Optional[str], Header(None, alias="X-User-Id")] = None,
) -> MCPRunResponse:
    """
    Direct endpoint for invoking the MCP agent orchestrator (run_mcp).

    Accepts JSON with:
      - 'query' (preferred) or legacy 'question'/'prompt'
      - 'files': list[str], 'topics': list[str], 'role': str, 'debug': bool
    Also accepts 'X-User-Id' header, which takes precedence over body.user_id.
    """
    # Robust JSON body parsing
    try:
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError("Body must be a JSON object")
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": "bad_request", "message": f"Invalid JSON: {e}"})

    # Backward-compat aliasing: prefer explicit 'query', otherwise 'question' or 'prompt'
    if "query" not in data:
        if "question" in data:
            data["query"] = data["question"]
        elif "prompt" in data:
            data["query"] = data["prompt"]

    # Validate with Pydantic (supports alias=question via model_config)
    try:
        payload = MCPRunRequest.model_validate(data)
    except Exception as e:
        # 422 with structured details
        raise HTTPException(status_code=422, detail={"error": "validation_error", "message": str(e)})

    # Finalize fields
    query = (payload.query or "").strip() or (payload.prompt or "").strip()
    if not query:
        raise HTTPException(status_code=422, detail={"error": "validation_error", "message": "Missing 'query'."})

    files = payload.files or []
    topics = payload.topics or []
    role = (payload.role or "planner").strip() or "planner"
    user_id = x_user_id or payload.user_id or "anonymous"
    debug = bool(payload.debug)

    # Basic type normalization for lists (defensive)
    if not isinstance(files, list):
        files = [str(files)]
    if not isinstance(topics, list):
        topics = [str(topics)]

    log_event(
        "mcp_run_received",
        {"user": user_id, "role": role, "files": len(files), "topics": len(topics), "debug": debug},
    )

    try:
        result = await run_mcp(
            query=query,
            files=files,
            topics=topics,
            role=role,
            user_id=user_id,
            debug=debug,
        )
        # Pass-through result shape; callers expect the MCP structure
        log_event("mcp_run_completed", {"user": user_id, "role": role})
        return result
    except HTTPException:
        # bubble existing HTTPExceptions unchanged
        raise
    except Exception as e:
        log_event("mcp_run_error", {"user": user_id, "role": role, "error": str(e)})
        raise HTTPException(status_code=500, detail={"error": "mcp_failed", "message": str(e)})
