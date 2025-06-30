# ──────────────────────────────────────────────────────────────────────────────
# File: routes/mcp.py
# Directory: routes/
# Purpose: API route for direct access to MCP handler (run_mcp) for testing, automation, or admin use
# ──────────────────────────────────────────────────────────────────────────────

from fastapi import APIRouter, HTTPException, Request, Header
from typing import Optional
from agents.mcp_agent import run_mcp

router = APIRouter(prefix="/mcp", tags=["mcp"])

@router.post("/run")
async def mcp_run(
    request: Request,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id")
):
    """
    Direct endpoint for invoking the MCP agent orchestrator (run_mcp).
    Accepts flexible input for query/prompt, plus optional files, topics, role, debug.
    """
    data = await request.json()
    # Accept a variety of possible input keys for maximum compatibility.
    query = data.get("query") or data.get("question") or data.get("prompt")
    if not query:
        raise HTTPException(status_code=422, detail="Missing 'query' in payload")

    # Use .get() with default empty list to prevent passing None if omitted.
    files = data.get("files", [])
    topics = data.get("topics", [])
    role = data.get("role", "planner")
    debug = data.get("debug", False)
    user_id = x_user_id or "anonymous"

    try:
        return await run_mcp(
            query=query,
            files=files,
            topics=topics,
            role=role,
            user_id=user_id,
            debug=debug,
        )
    except Exception as e:
        # Optionally add traceback.print_exc() for debug
        raise HTTPException(status_code=500, detail=f"MCP error: {str(e)}")
