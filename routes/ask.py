# File: routes/ask.py
# Directory: routes/
# Purpose: API routes for user agent interactions (GET, POST, stream) with context generation,
# memory logging, action queuing, and OpenAI test endpoint.

import os, json, uuid, logging, datetime, traceback
from fastapi import APIRouter, Query, Request, Header, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional, AsyncGenerator
from services.context_engine import ContextEngine
from services.agent import answer
from services.memory import summarize_memory_entry, save_memory_entry
from openai import OpenAIError

router = APIRouter(prefix="/ask", tags=["ask"])
QUEUE_PATH = "./logs/queue.jsonl"

def queue_action(action: dict, context: str, user: str) -> str:
    id = str(uuid.uuid4())
    timestamp = datetime.datetime.utcnow().isoformat() + "Z"
    entry = {
        "id": id,
        "timestamp": timestamp,
        "status": "pending",
        "action": { **action, "context": context },
        "history": [ { "timestamp": timestamp, "status": "queued", "user": user } ]
    }
    with open(QUEUE_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return id

def log_interaction(user_id, question, context, response):
    ts = datetime.datetime.utcnow().isoformat()
    preview = str(response)[:80].replace("\n", " ")
    logging.info(f"{ts}\t{user_id}\tQ: {question}\tCTX: {len(context)} chars\tA: {preview}")

# === GET /ask ===
@router.get("")
async def ask_get(
    request: Request,
    question: str = Query(...),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    debug: Optional[bool] = Query(False)
):
    user_id = x_user_id or "anonymous"
    try:
        ce = ContextEngine(user_id=user_id)
        context = ce.build_context(question)
        result = await answer(user_id, question, context=context)

        # Handle raw string or dict
        if isinstance(result, str):
            response = result
            action = None
        else:
            response = result.get("response", "")
            action = result.get("action")

        id = queue_action(action, context, user_id) if action else None
        summary = summarize_memory_entry(question, response, context, [action] if action else [], user_id)
        save_memory_entry(user_id, summary)
        log_interaction(user_id, question, context, response)

        out = { "response": response, "id": id }
        if action: out["action"] = action
        if debug: out["context"] = context
        return out
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# === POST /ask ===
@router.post("")
async def ask_post(
    request: Request,
    payload: dict,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    debug: Optional[bool] = Query(False)
):
    user_id = x_user_id or "anonymous"
    question = payload.get("question", "")
    if not question:
        raise HTTPException(status_code=422, detail="Missing 'question' in request payload.")
    try:
        ce = ContextEngine(user_id=user_id)
        context = ce.build_context(question)
        result = await answer(user_id, question, context=context)

        if isinstance(result, str):
            response = result
            action = None
        else:
            response = result.get("response", "")
            action = result.get("action")

        id = queue_action(action, context, user_id) if action else None
        summary = summarize_memory_entry(question, response, context, [action] if action else [], user_id)
        save_memory_entry(user_id, summary)
        log_interaction(user_id, question, context, response)

        out = { "response": response, "id": id }
        if action: out["action"] = action
        if debug: out["context"] = context
        return out
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# === POST /ask/stream ===
@router.post("/stream")
async def ask_stream(
    request: Request,
    payload: dict,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id")
):
    user_id = x_user_id or "anonymous"
    question = payload.get("question", "")
    if not question:
        raise HTTPException(status_code=422, detail="Missing 'question' in request payload.")
    try:
        ce = ContextEngine(user_id=user_id)
        context = ce.build_context(question)
        full_response = []
        captured_action = None

        async def streamer() -> AsyncGenerator[str, None]:
            nonlocal captured_action
            async for chunk in answer(user_id, question, context=context, stream=True):
                full_response.append(chunk)
                yield chunk

            # Try to parse as final JSON payload
            try:
                joined = "".join(full_response)
                maybe_json = json.loads(joined)
                if isinstance(maybe_json, str):
                    full_response[:] = [maybe_json]
                elif isinstance(maybe_json, dict):
                    full_response[:] = [maybe_json.get("response", "")]
                    captured_action = maybe_json.get("action")
            except Exception:
                pass

        response = StreamingResponse(streamer(), media_type="text/plain")

        async def finalize_log():
            await response.body_iterator.aclose()
            response_text = "".join(full_response)
            summary = summarize_memory_entry(
                prompt=question,
                response=response_text,
                context=context,
                actions=[captured_action] if captured_action else [],
                user_id=user_id
            )
            save_memory_entry(user_id, summary)
            log_interaction(user_id, question, context, response_text)
            if captured_action:
                queue_action(captured_action, context, user_id)

        response.background = finalize_log()
        return response
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# === GET /ask/test_openai ===
@router.get("/test_openai")
async def test_openai():
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Ping test"}
            ]
        )
        return { "response": response.choices[0].message.content }
    except OpenAIError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
