# routes/ask.py (CORS-safe, Railway-ready)
import os
import re
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from services import agent

router = APIRouter(prefix="/ask", tags=["ask"])

# === Allow CORS preflight OPTIONS without auth ===
@router.options("/{path:path}")
async def handle_options(_: Request):
    return JSONResponse(status_code=200)

# === Simple API key header auth ===
def auth(x_api_key: str = Header(..., alias="X-API-Key")):
    if x_api_key != os.getenv("API_KEY"):
        raise HTTPException(status_code=401, detail="bad key")

# === GET support for legacy /ask?q=... ===
@router.get("")
async def ask_get(q: str, user=Depends(auth)):
    answer_text: str = await agent.answer(q)
    return {"answer": answer_text}

# === POST support for JSON { "q": "..." } ===
@router.post("")
async def ask_post(request: Request, user=Depends(auth)):
    data = await request.json()
    q = data.get("q")
    if not q:
        raise HTTPException(status_code=400, detail="Missing 'q' in request body")
    answer_text: str = await agent.answer(q)
    return {"answer": answer_text}
