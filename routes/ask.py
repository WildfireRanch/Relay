# ──────────────────────────────────────────────────────────────────────────────
# File: ask.py
# Directory: routes/
# Purpose : API routes for user agent interactions (GET, POST, stream) with
#           tiered context generation, deep memory logging, and patch queuing.
# ──────────────────────────────────────────────────────────────────────────────

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

# === Patch Queue Helper ========================================================
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

# === GET /ask ==================================================================
@router.get("")
async def ask_get(
    request: Request,
    question: str = Query(...),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    debug: Optional[bool] = Query(False),
    reflect: Optional[bool] = Query(False),
    score_threshold: Optional[float] = Query(None)
):
    user_id = x_user_id or "anonymous"
    try:
        threshold_env = os.getenv("KB_SCORE_THRESHOLD")
        threshold = score_threshold if score_threshold is not None else float(threshold_env) if threshold_env else None

        ce = ContextEngine(user_id=user_id)
        context_result = ce.build_context(question, score_threshold=threshold, return_debug=debug)
        context = context_result["prompt"] if isinstance(context_result, dict) else context_result
        files_used = context_result.get("files_used", []) if isinstance(context_result, dict) else []

        result = await answer(user_id, question, context=context, reflect=reflect)
        response = result if isinstance(result, str) else result.get("response", "")
        action = None if isinstance(result, str) else result.get("action")
        id = queue_action(action, context, user_id) if action else None

        # Log interaction
        entry = summarize_memory_entry(
            prompt=question,
            response=response,
            context=context,
            actions=[action] if action else [],
            user_id=user_id,
            context_files=[f.get("path") or f.get("title") for f in files_used],
            used_global_context=any("global" in (f.get("tier") or "") for f in files_used),
            fallback=False,
            prompt_length=len(question + context),
            response_length=len(response)
        )
        save_memory_entry(user_id, entry)
        log_interaction(user_id, question, context, response)

        out = { "response": response, "id": id }
        if action: out["action"] = action
        if debug:
            out["context"] = context
            out["files_used"] = files_used
        return out

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# === POST /ask =================================================================
@router.post("")
async def ask_post(
    request: Request,
    payload: dict,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    debug: Optional[bool] = Query(False),
    reflect: Optional[bool] = Query(False),
    score_threshold: Optional[float] = Query(None)
):
    user_id = x_user_id or "anonymous"
    question = payload.get("question", "")
    if not question:
        raise HTTPException(status_code=422, detail="Missing 'question' in request payload.")
    try:
        threshold_env = os.getenv("KB_SCORE_THRESHOLD")
        threshold = score_threshold if score_threshold is not None else float(threshold_env) if threshold_env else None

        ce = ContextEngine(user_id=user_id)
        context_result = ce.build_context(question, score_threshold=threshold, return_debug=debug)
        context = context_result["prompt"] if isinstance(context_result, dict) else context_result
        files_used = context_result.get("files_used", []) if isinstance(context_result, dict) else []

        result = await answer(user_id, question, context=context, reflect=reflect)
        response = result if isinstance(result, str) else result.get("response", "")
        action = None if isinstance(result, str) else result.get("action")
        id = queue_action(action, context, user_id) if action else None

        # Log memory
        entry = summarize_memory_entry(
            prompt=question,
            response=response,
            context=context,
            actions=[action] if action else [],
            user_id=user_id,
            topics=payload.get("topics"),
            files=payload.get("files"),
            context_files=[f.get("path") or f.get("title") for f in files_used],
            used_global_context=any("global" in (f.get("tier") or "") for f in files_used),
            fallback=False,
            prompt_length=len(question + context),
            response_length=len(response)
        )
        save_memory_entry(user_id, entry)
        log_interaction(user_id, question, context, response)

        out = { "response": response, "id": id }
        if action: out["action"] = action
        if debug:
            out["context"] = context
            out["files_used"] = files_used
        return out

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# === POST /ask/stream ==========================================================
@router.post("/stream")
async def ask_stream(
    request: Request,
    payload: dict,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    reflect: Optional[bool] = Query(False),
    score_threshold: Optional[float] = Query(None)
):
    user_id = x_user_id or "anonymous"
    question = payload.get("question", "")
    if not question:
        raise HTTPException(status_code=422, detail="Missing 'question' in request payload.")

    try:
        threshold_env = os.getenv("KB_SCORE_THRESHOLD")
        threshold = score_threshold if score_threshold is not None else float(threshold_env) if threshold_env else None

        ce = ContextEngine(user_id=user_id)
        context = ce.build_context(question, score_threshold=threshold)
        context_files = []
        full_response = []
        captured_action = None

        async def streamer() -> AsyncGenerator[str, None]:
            nonlocal captured_action
            async for chunk in answer(user_id, question, context=context, stream=True, reflect=reflect):
                full_response.append(chunk)
                yield chunk
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
            entry = summarize_memory_entry(
                prompt=question,
                response=response_text,
                context=context,
                actions=[captured_action] if captured_action else [],
                user_id=user_id,
                context_files=context_files,
                used_global_context="global_context.md" in context,
                fallback=False,
                prompt_length=len(question + context),
                response_length=len(response_text)
            )
            save_memory_entry(user_id, entry)
            log_interaction(user_id, question, context, response_text)
            if captured_action:
                queue_action(captured_action, context, user_id)

        response.background = finalize_log()
        return response

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# === GET /ask/test_openai ======================================================
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
