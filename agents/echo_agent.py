# File: echo_agent.py
# Directory: agents
# Purpose: Final answer synthesis for /ask. Prefer concise, answer-first replies.
#          Honors Planner fast-path via `plan.final_answer`. If the model parrots
#          (e.g., "Define what ...", "What is ..."), synthesize a definition from
#          provided CONTEXT instead of returning the parrot.
#
# Upstream:
#   - ENV (required): OPENAI_API_KEY
#   - ENV (optional):
#       ECHO_MODEL         (default "gpt-4o-mini")
#       ECHO_MAX_TOKENS    (default 700)
#       ECHO_TEMPERATURE   (default 0.2)
#       ECHO_TIMEOUT_S     (default 45)
#       ECHO_MAX_RETRIES   (default 2)
#   - Imports: os, asyncio, typing, re, openai, utils.openai_client, core.logging
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
import re
import asyncio
from typing import Dict, Optional, AsyncGenerator, List

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
    "- Do not restate the question or ask the user to define it.\n"
    "- If you cannot find enough details, say so briefly.\n"
)

# ---- Helpers ---------------------------------------------------------------------------------

_DEFN_PREFIXES = ("what is", "who is", "define", "describe")
_PARROT_PAT = re.compile(r"^\s*(what\s+is|who\s+is|define|describe)\b", re.I)

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_TITLE_LINE = re.compile(r"^\s*(#+\s*)?(.+?):\s*$")

def _is_definitional(q: str) -> bool:
    return (q or "").strip().lower().startswith(_DEFN_PREFIXES)

def _split_paragraphs(text: str) -> List[str]:
    if not text:
        return []
    # Prefer double-newline paragraphing; fallback to single
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    if parts:
        return parts
    return [p.strip() for p in text.split("\n") if p.strip()]

def _synthesize_definition_from_context(query: str, context: str, max_chars: int = 550) -> Optional[str]:
    """
    Deterministic definition extractor from CONTEXT:
    - Find a paragraph mentioning the first 3 meaningful words of the query (case-insensitive).
    - If none, try first non-empty paragraph under a header like 'Overview'/'Summary'.
    - Return 2–4 sentences, trimmed to max_chars.
    """
    if not context:
        return None

    # derive a simple key from query
    q_words = re.findall(r"[A-Za-z0-9\-_/]+", query or "")
    key = " ".join(q_words[:3]).lower()

    paras = _split_paragraphs(context)
    cand = None

    # 1) direct mention of the key
    if key:
        for p in paras:
            if key in p.lower():
                cand = p
                break

    # 2) look for an 'Overview'/'Summary' block if no direct hit
    if not cand:
        for i, p in enumerate(paras):
            if _TITLE_LINE.match(p) and any(h in p.lower() for h in ("overview", "summary", "definition")):
                if i + 1 < len(paras):
                    cand = paras[i + 1]
                    break

    # 3) fallback to first paragraph
    if not cand and paras:
        cand = paras[0]

    if not cand:
        return None

    # compose 2–4 sentences
    sents = [s.strip() for s in _SENT_SPLIT.split(cand) if s.strip()]
    if not sents:
        return None
    out = " ".join(sents[:4]).strip()
    if len(out) > max_chars:
        out = out[:max_chars].rstrip() + "…"

    # must not be a parrot
    if _PARROT_PAT.match(out):
        return None
    return out or None

def _looks_like_parrot(text: str) -> bool:
    """Heuristic: starts with 'what is/define/describe' and mentions the same noun."""
    if not text:
        return False
    return bool(_PARROT_PAT.match(text))

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
    If the model parrots, synthesize an answer from CONTEXT instead.
    Returns both 'answer' and 'response' for backward compatibility.
    """
    try:
        # 1) Planner fast-path (no extra LLM call)
        if isinstance(plan, dict) and isinstance(plan.get("final_answer"), str):
            ans = plan["final_answer"].strip()
            if ans:
                log_event("echo_fastpath_plan_answer", {"user": user_id, "len": len(ans)})
                return {"answer": ans, "response": ans, "route": "echo"}

        # 2) Build messages; steer definitional prompts to be concise
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

        # 3) Small async retry loop
        last_err: Optional[Exception] = None
        reply = ""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                reply = await _chat_once(messages)
                if not reply:
                    raise OpenAIError("Empty content from model")
                break
            except Exception as e:
                last_err = e
                wait = min(6, 2 ** (attempt - 1))
                log_event("echo_llm_retry", {"attempt": attempt, "wait_s": wait, "error": str(e)})
                await asyncio.sleep(wait)
        if not reply and last_err:
            raise OpenAIError(f"Echo LLM failed after {MAX_RETRIES} attempts: {last_err}")

        # 4) Anti-parrot guard: if reply is a restated prompt, synthesize from CONTEXT
        if _looks_like_parrot(reply):
            synth = _synthesize_definition_from_context(query, context)
            if synth:
                log_event("echo_antiparrot_synth", {"user": user_id, "chars": len(synth)})
                reply = synth

        # 5) Finalize
        log_event("echo_agent_reply", {"user": user_id, "reply_head": reply[:500]})
        return {"answer": reply, "response": reply, "route": "echo"}

    except Exception as e:
        log_event("echo_agent_error", {"error": str(e), "user_id": user_id, "query": (query or "")[:300]})
        msg = "[Echo failed to respond. Please try again.]"
        return {"answer": msg, "response": msg, "route": "echo"}

async def stream(
    query: str,
    context: str = "",
    user_id: str = "anonymous",
) -> AsyncGenerator[str, None]:
    """
    Stream a response token-by-token. Minimal path; planner fast-path handled by non-stream run().
    """
    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"QUESTION:\n{query}\n\nCONTEXT:\n{context or '[none]'}"},
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
        log_event("echo_agent_stream_error", {"error": str(e), "user_id": user_id, "query": (query or '')[:300]})
        yield f"[Error] Echo stream failed: {str(e)}"
