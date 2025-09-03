# File: routes/ask_stream.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from agents import mcp_agent

router = APIRouter()

@router.post("/ask/stream")
async def ask_stream(body: dict):
    async def gen():
        # start MCP with a streamed agent (if available), else chunk the final answer
        res = await mcp_agent.run_mcp(query=body.get("query",""), files=body.get("files") or [], topics=body.get("topics") or [], role=body.get("role","planner"), user_id=body.get("user_id","anonymous"), debug=bool(body.get("debug")))
        txt = (res.get("final_text") or "").split()
        yield f"data: {res.get('meta')}\n\n"  # first meta frame
        buf = []
        for w in txt:
            buf.append(w)
            if len(buf) >= 30:
                yield f"data: {' '.join(buf)} \n\n"; buf.clear()
        if buf: yield f"data: {' '.join(buf)} \n\n"
        yield "event: done\ndata: {}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")
