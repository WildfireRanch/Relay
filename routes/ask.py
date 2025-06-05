from fastapi import APIRouter, Query
from services.agent import answer, client
from openai import OpenAIError

# Create the FastAPI router
router = APIRouter()

# === GET-based /ask endpoint ===
# Usage: /ask?question=your+query
@router.get("/ask")
async def ask_get(question: str = Query(..., description="User query")):
    try:
        print(f"[ask.py] Received GET question: {question}")
        response = await answer(question)
        return {"response": response}
    except Exception as e:
        # Print traceback to Railway logs for debugging
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

# === POST-based /ask endpoint ===
# Usage: POST /ask with JSON payload: { "question": "your query" }
@router.post("/ask")
async def ask_post(payload: dict):
    try:
        question = payload.get("question", "")
        print(f"[ask.py] Received POST question: {question}")
        response = await answer(question)
        return {"response": response}
    except Exception as e:
        # Full traceback for better error visibility
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

# === /test_openai route ===
# Purpose: Isolate and verify that OpenAI API is working from Railway
@router.get("/test_openai")
async def test_openai():
    try:
        print("[test_openai] Sending test request to OpenAI...")
        response = await client.chat.completions.create(
            model="gpt-4o",  # Change this if you're using a different model
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Ping test"}
            ]
        )
        return {"response": response.choices[0].message.content}
    except OpenAIError as e:
        # Specific OpenAI API errors
        print("❌ OpenAIError:", e)
        return {"error": str(e)}
    except Exception as e:
        # Catch-all fallback for unexpected issues
        import traceback
        traceback.print_exc()
        return {"error": f"Unexpected error: {str(e)}"}
