# ──────────────────────────────────────────────────────────────────────────────
# File: agents/critic_agent.py
# Purpose: Multi-critic QA layer for validating planner output in MCP
# Also handles fallback response for misrouted GPT classifications
# ──────────────────────────────────────────────────────────────────────────────

import os
import traceback
import asyncio
import logging
import datetime
from openai import AsyncOpenAI
from core.logging import log_event
from services.memory import save_memory_entry

MODEL = os.getenv("CRITIC_MODEL", "gpt-4o")
openai = AsyncOpenAI()

# === System Prompts for Critics ===
STRUCTURE_PROMPT = """
You are a JSON schema validator for an AI planner. Check that the input plan has:
- An `objective` string
- A `steps` list of strings (non-empty)
- A `recommendation` string
Return a JSON with `passes` (true/false) and `issues` (list of problems).
""".strip()

LOGIC_PROMPT = """
You are a logic and reasoning critic. Review this plan and:
- Identify contradictions or unsupported steps
- Flag vague or circular logic
Respond with JSON: `passes` (true/false), `issues` (list of feedback).
""".strip()

SAFETY_PROMPT = """
You are a safety auditor. Determine if any steps could:
- Cause irreversible damage
- Affect live systems without confirmation
- Seem dangerously vague
Return JSON: `passes`, `issues`
""".strip()

# === Base helper to run a single critic ===
async def run_critic(prompt: str, input_block: str, label: str) -> dict:
    try:
        response = await openai.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": input_block}
            ],
            temperature=0.2,
            response_format="json"
        )
        result = eval(response.choices[0].message.content)
        return {"name": label, **result}
    except Exception as e:
        log_event("critic_error", {"critic": label, "error": str(e), "trace": traceback.format_exc()})
        return {"name": label, "passes": False, "issues": [f"Error during {label} critic execution"]}

# === Individual critics ===
async def structure(plan: dict) -> dict:
    return await run_critic(STRUCTURE_PROMPT, str(plan), "structure")

async def logic(plan: dict, context: str) -> dict:
    block = f"Context:\n{context}\n\nPlan:\n{plan}"
    return await run_critic(LOGIC_PROMPT, block, "logic")

async def safety(plan: dict, context: str) -> dict:
    block = f"Context:\n{context}\n\nPlan:\n{plan}"
    return await run_critic(SAFETY_PROMPT, block, "safety")

# === Run all critics in parallel ===
async def run_all(plan: dict, context: str) -> list[dict]:
    results = await asyncio.gather(
        structure(plan),
        logic(plan, context),
        safety(plan, context)
    )
    return results

# === Fallback handler for routing failures ===
async def handle_routing_error(
    user_id: str,
    query: str,
    original_label: str,
    context: str = "",
    reason: str = "unrecognized_gpt_label"
) -> dict:
    """
    Called when GPT produces an invalid routing label (e.g., 'banana').
    Logs the issue, returns a fallback response, and optionally tags memory.
    """
    fallback_response = (
        f"⚠️ I wasn’t sure how to route this task (GPT said '{original_label}'). "
        "I’ve defaulted to general assistant mode. Let me know if you'd like a retry or manual override."
    )

    log_entry = {
        "user": user_id,
        "query": query,
        "label": original_label,
        "context_chars": len(context),
        "reason": reason,
        "timestamp": datetime.datetime.utcnow().isoformat()
    }

    logging.warning(f"[critic_agent] Routing failure: {log_entry}")

    save_memory_entry(user_id, {
        "prompt": query,
        "response": fallback_response,
        "context": context,
        "actions": [],
        "critic": True,
        "tags": ["routing_error", "fallback"],
        "meta": {
            "original_label": original_label,
            "reason": reason,
            "context_chars": len(context)
        },
        "timestamp": log_entry["timestamp"],
        "prompt_length": len(query + context),
        "response_length": len(fallback_response),
        "fallback": True
    })

    return {
        "response": fallback_response,
        "action": None,
        "critic_log": log_entry
    }
