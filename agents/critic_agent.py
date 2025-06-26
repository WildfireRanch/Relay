# ──────────────────────────────────────────────────────────────────────────────
# File: agents/critic_agent.py
# Purpose: Logs and responds to invalid GPT classifications or agent failures.
# Used when planner misroutes or cannot confidently assign a task type.
# ──────────────────────────────────────────────────────────────────────────────

import logging
import datetime
from services.memory import save_memory_entry

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

    # Structured logging
    logging.warning(f"[critic_agent] Routing failure: {log_entry}")

    # Optional: Log to memory for long-term review
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
            "context_chars": len(context),
        },
        "timestamp": log_entry["timestamp"],
        "prompt_length": len(query + context),
        "response_length": len(fallback_response),
        "fallback": True,
    })

    return {
        "response": fallback_response,
        "action": None,
        "critic_log": log_entry
    }
