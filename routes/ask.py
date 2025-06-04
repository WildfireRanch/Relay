# routes/ask.py
import os
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from services import agent

# Prefix /ask for all routes in this module
router = APIRouter(prefix="/ask", tags=["ask"])

# === Simple header-based auth ===
def auth(x_api_key: str = Header(..., alias="X-API-Key")):
    """
    Simple API key check from header: X-API-Key
    Validates against the API_KEY defined in your environment
    """
    if x_api_key != os.getenv("API_KEY"):
        raise HTTPException(status_code=401, detail="bad key")

# === Handle preflight CORS request ===
@router.options("")  # Matches /ask exactly
async def handle_options(request: Request):
    """
    Allow CORS preflight OPTIONS requests so browsers can POST
    """
    return JSONResponse(status_code=200)

# === GET ask route ===
@router.get("")  # No trailing slash keeps canonical /ask
async def ask_get(q: str, user=Depends(auth)):
    """
    Accepts query string param `q`, returns Echo agent's answer
    Requires valid X-API-Key header
    """
    answer_text: str = await agent.answer(q)
    return {"answer": answer_text}

# === POST ask route ===
@router.post("")
async def ask_post(request: Request, user=Depends(auth)):
    """
    Accepts JSON payload { "q": "your question" }, returns agent answer
    Enables POST usage with CORS-safe headers
    """
    data = await request.json()
    q = data.get("q")
    if not q:
        raise HTTPException(status_code=400, detail="Missing 'q' in request body")
    answer_text: str = await agent.answer(q)
    return {"answer": answer_text}

