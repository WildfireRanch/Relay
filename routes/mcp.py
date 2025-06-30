from fastapi import APIRouter, HTTPException, Request, Header
from typing import Optional
from agents.mcp_agent import run_mcp

router = APIRouter(prefix="/mcp", tags=["mcp"])

@router.post("/run")
async def mcp_run(
    request: Request,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id")
):
    data = await request.json()
    query = data.get("query") or data.get("question") or data.get("prompt")
    if not query:
        raise HTTPException(status_code=422, detail="Missing 'query' in payload")
    files = data.get("files")
    topics = data.get("topics")
    role = data.get("role", "planner")
    debug = data.get("debug", False)
    user_id = x_user_id or "anonymous"
    return await run_mcp(
        query=query,
        files=files,
        topics=topics,
        role=role,
        user_id=user_id,
        debug=debug,
    )

