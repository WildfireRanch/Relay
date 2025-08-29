# File: echo_agent.py
# Directory: agents
# Purpose: Final answer synthesis for /ask. Prefer concise, answer-first replies.
#          Honors Planner fast-path via `plan.final_answer` when available.
#
# Upstream:
#   - ENV (required): OPENAI_API_KEY
#   - ENV (optional):
#       ECHO_MODEL         (default "gpt-4o-mini")
#       ECHO_MAX_TOKENS    (default 700)
#       ECHO_TEMPERATURE   (default 0.2)
#       ECHO_TIMEOUT_S     (default 45)
#       ECHO_MAX_RETRIES   (default 2)     # logical retries here (not httpx transport)
#   - Imports: os, asyncio, typing, openai, utils.openai_client, core.logging
#
# Downstream:
#   - agents.mcp_agent (primary caller)
#   - routes.ask (indirectly via MCP)
#
# Contents:
#   - run(query, context="", user_id="anonymous", plan=None) -> dict
#   - stream(query, context="", user_id="anonymous") -> async generator

from __future__ import annotations

import os
import asyncio
from typing import Dict, Optional, AsyncGenerator

from openai import APIError as OpenAIError
from core.logging import log_event
from utils.openai_client import create_openai_client

# ---- Model / generation config ---------------------------------------------------------------

MODEL = os.getenv("ECHO_MODEL", "gpt-4o-mini")
MAX_TOKENS = int(os.getenv("ECHO_MAX_TOKENS", "700"))
TEMPERATURE = float(os.getenv("ECHO_TEMPERATURE", "0.2"))
TIMEOUT_S = int(os.getenv("ECHO_TIMEOUT_S", "45"))
MAX_RETRIES = int(os.getenv("ECHO_MAX_RETRIES", "2"))

_openai = create_openai_client()

SYSTEM_PROMPT = (
    "You are Echo. Answer directly and succinctly.\n"
    "- Provide a short, factual answer first (2–4 sentences).\n"
    "- Use the provided CONTEXT when it improves accuracy.\n"
    "- Do not restate the question or outline a plan unless asked.\n"
    "- If sources are present in CONTEXT, you may append a brief 'Sources:' list (1–3).\n"
)

# ---- Helpers ---------------------------------------------------------------------------------


def _is_definitional(q: str) -> bool:
    ql = (q or "").strip().lower()
    return (
        ql.startswith("what is")
        or ql.startswith("who is")
        or ql.startswith("define ")
        or ql.startswith("describe ")
    )


async def _chat_once(messages: list[dict]) -> str:
    resp = await _openai.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        timeout=TIMEOUT_S,
    )
    return (resp.choices[0].message.content or "").strip()


# ---- Public API ------------------------------------------------------------------------------


async def run(
    query: str,
    context: str = "",
    user_id: str = "anonymous",
    plan: Optional[Dict] = None,
) -> Dict[str, str]:
    """
    Produce a concise answer. If planner provided `final_answer`, surface it immediately.
    Returns both 'answer' and 'response' for backward compatibility.
    """
    try:
        # 1) Planner fast-path (no extra LLM call if we already have a crisp answer)
        if isinstance(plan, dict) and isinstance(plan.get("final_answer"), str):
            ans = plan["final_answer"].strip()
            if ans:
                log_event("echo_fastpath_plan_answer", {"user": user_id, "len": len(ans)})
                return {"answer": ans, "response": ans, "route": "echo"}

        # 2) Build messages; steer definitional queries to be concise
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if _is_definitional(query):
            user_content = (
                "Provide a concise 2–4 sentence definition/answer using the CONTEXT when helpful.\n"
                f"QUESTION:\n{query}\n\nCONTEXT:\n{context or '[none]'}"
            )
        else:
            user_content = (
                "Answer directly using the CONTEXT when helpful.\n"
                f"QUESTION:\n{query}\n\nCONTEXT:\n{context or '[none]'}"
            )
        messages.append({"role": "user", "content": user_content})

        # 3) Small async retry loop (logical retries live here, not in httpx transport)
        last_err: Optional[Exception] = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                reply = await _chat_once(messages)
                if not reply:
                    raise OpenAIError("Empty content from model")
                log_event(
                    "echo_agent_reply",
                    {"user": user_id, "reply_head": reply[:500], "attempt": attempt},
                )
                return {"answer": reply, "response": reply, "route": "echo"}
            except Exception as e:
                last_err = e
                wait = min(6, 2 ** (attempt - 1))
                log_event(
                    "echo_llm_retry",
                    {"attempt": attempt, "wait_s": wait, "error": str(e)},
                )
                await asyncio.sleep(wait)

        # Retries exhausted
        raise OpenAIError(f"Echo LLM failed after {MAX_RETRIES} attempts: {last_err}")

    except Exception as e:
        log_event("echo_agent_error", {"error": str(e), "user_id": user_id, "query": query[:300]})
        # Keep a usable response shape on failure
        msg = "[Echo failed to respond. Please try again.]"
        return {"answer": msg, "response": msg, "route": "echo"}


async def stream(
    query: str,
    context: str = "",
    user_id: str = "anonymous",
) -> AsyncGenerator[str, None]:
    """
    Stream a response token-by-token. Note: This is a simple streaming path;
    it does not include planner fast-path logic.
    """
    try:
        # Minimal prompt for streaming; callers can enhance if needed
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"QUESTION:\n{query}\n\nCONTEXT:\n{context or '[none]'}",
            },
        ]
        response_stream = await _openai.chat.completions.create(
            model=MODEL,
            messages=messages,
            stream=True,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            timeout=TIMEOUT_S,
        )
        async for chunk in response_stream:
            delta = getattr(chunk.choices[0].delta, "content", None)
            if delta:
                yield delta
    except Exception as e:
        log_event("echo_agent_stream_error", {"error": str(e), "user_id": user_id, "query": query[:300]})
        yield f"[Error] Echo stream failed: {str(e)}"
