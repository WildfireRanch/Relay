# File: ask.py
# Directory: routes/
# Purpose: API routes for user chat/ask endpoint with per-user memory, multi-turn support, and OpenAI test.

import os
from fastapi import APIRouter, Query, Request, Header, HTTPException
from fastapi.responses import JSONResponse
from services.agent import answer
from openai import OpenAIError
from typing import Optional

router = APIRouter()

# === GET-based /ask endpoint ===
# Usage: GET /ask?question=your+query
@router.get("/ask")
async def ask_get(
    request: Request,
    question: str = Query(..., description="User query"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id")
):
    """
    Handle GET requests to /ask.
    Extracts user_id from header for multi-turn context.
    """
    user_id = x_user_id or "anonymous"
    try:
        print(f"[ask.py] Received GET question from {user_id}: {question}")
        response = await answer(user_id, question)
        return {"response": response}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# === POST-based /ask endpoint ===
# Usage: POST /ask with JSON payload: { "question": "your query" }
@router.post("/ask")
async def ask_post(
    request: Request,
    payload: dict,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id")
):
    """
    Handle POST requests to /ask.
    Extracts user_id from header for multi-turn context.
    """
    user_id = x_user_id or "anonymous"
    question = payload.get("question", "")
    if not question:
        raise HTTPException(status_code=422, detail="Missing 'question' in request payload.")
    try:
        print(f"[ask.py] Received POST question from {user_id}: {question}")
        response = await answer(user_id, question)
        return {"response": response}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# === /test_openai route ===
# Purpose: Verify OpenAI API connectivity (for debugging only)
@router.get("/test_openai")
async def test_openai():
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    try:
        print("[test_openai] Sending test request to OpenAI...")
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Ping test"}
            ]
        )
        return {"response": response.choices[0].message.content}
    except OpenAIError as e:
        print("❌ OpenAIError:", e)
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
