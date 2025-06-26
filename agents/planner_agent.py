# ──────────────────────────────────────────────────────────────────────────────
# File: agents/planner_agent.py
# Purpose: Central AI router for all user queries (Echo, Docs, Control, Codex)
# ──────────────────────────────────────────────────────────────────────────────

import os, json, uuid, logging, datetime
from typing import Optional, AsyncGenerator

from openai import AsyncOpenAI
from fastapi.responses import StreamingResponse

from services.context_engine import ContextEngine
from services.memory import summarize_memory_entry, save_memory_entry
from agents import codex_agent, docs_agent, control_agent, echo_agent

# === Constants & Settings ===
QUEUE_PATH = "./logs/queue.jsonl"
AGENT_LABELS = {"codex", "docs", "control", "echo"}
GPT_CLASSIFY_PROMPT = [
    {
        "role": "system",
        "content": (
            "You are a task router for an AI assistant. "
            "Classify the user's request into one of these categories:\n\n"
            "- codex → code generation, refactoring, patching\n"
            "- docs → summarizing or querying documents\n"
            "- control → executing actions or commands\n"
            "- echo → general assistant or fallback\n\n"
            "Respond with one word: codex, docs, control, or echo."
        )
    }
]

# === Utilities ===
def get_openai_key() -> str:
    return os.getenv("OPENAI_API_KEY", "")

def queue_action(action: Optional[dict], context: str, user: str) -> Optional[str]:
    if not action:
        return None
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

# === Core Entry Point ===
async def handle_query(
    user_id: str,
    query: str,
    reflect: bool = False,
    debug: bool = False,
    score_threshold: Optional[float] = None,
    payload: Optional[dict] = None
) -> dict:
    # 1. Build context
    ce = ContextEngine(user_id=user_id)
    context_result = ce.build_context(query, score_threshold=score_threshold, return_debug=debug)
    context = context_result.get("prompt", "") if isinstance(context_result, dict) else context_result
    files_used = context_result.get("files_used", []) if isinstance(context_result, dict) else []

    # 2. Classify via GPT
    agent_label = "echo"
    original_label = "echo"
    try:
        client = AsyncOpenAI(api_key=get_openai_key())
        classification = await client.chat.completions.create(
            model="gpt-4o",
            messages=GPT_CLASSIFY_PROMPT + [{ "role": "user", "content": query }]
        )
        original_label = classification.choices[0].message.content.strip().lower()
        agent_label = original_label if original_label in AGENT_LABELS else "echo"
        if agent_label != original_label:
            logging.warning(f"[planner] Invalid agent label from GPT: {original_label!r} → fallback to 'echo'")
    except Exception as e:
        logging.error(f"[planner] GPT classification failed: {e}")
        original_label = "gpt_error"

    # 3. Route to appropriate agent
    if agent_label == "codex":
        result = await codex_agent.handle(user_id, query, context)
    elif agent_label == "docs":
        result = await docs_agent.handle(user_id, query, context)
    elif agent_label == "control":
        result = await control_agent.handle(user_id, query, context)
    else:
        result = await echo_agent.handle(user_id, query, context, reflect=reflect)

    # 4. If misclassified, log critic fallback
    if agent_label == "echo" and original_label != "echo":
        from agents import critic_agent
        critic_result = await critic_agent.handle_routing_error(user_id, query, original_label, context)
        result = {
            "response": result.get("response", "") + "\n\n" + critic_result["response"],
            "action": result.get("action")
        }

    # 5. Normalize result
    response = result.get("response", "") if isinstance(result, dict) else str(result)
    action = result.get("action") if isinstance(result, dict) else None
    task_id = queue_action(action, context, user_id)

    # 6. Log memory
    entry = summarize_memory_entry(
        prompt=query,
        response=response,
        context=context,
        actions=[action] if action else [],
        user_id=user_id,
        topics=(payload or {}).get("topics"),
        files=(payload or {}).get("files"),
        context_files=[f.get("path") or f.get("title") for f in files_used],
        used_global_context=any("global" in (f.get("tier") or "") for f in files_used),
        fallback=False,
        prompt_length=len(query + context),
        response_length=len(response)
    )
    save_memory_entry(user_id, entry)
    log_interaction(user_id, query, context, response)

    return {
        "response": response,
        "id": task_id,
        "action": action,
        **({"context": context, "files_used": files_used} if debug else {})
    }

# === Streaming Support (echo only) ===
async def handle_stream(user_id: str, query: str, reflect: bool = False) -> StreamingResponse:
    async def streamer() -> AsyncGenerator[str, None]:
        try:
            async for chunk in echo_agent.stream(user_id, query, reflect=reflect):
                yield chunk
        except Exception as e:
            yield f"\n[Error during streaming: {str(e)}]"

    return StreamingResponse(streamer(), media_type="text/plain")
