# File: echo_agent.py
# Directory: agents
# Purpose: Final answer synthesis for /ask. Prefer concise, answer-first replies.
#          Honors Planner fast-path via `plan.final_answer`. If the model parrots
#          (e.g., "Define what ...", "What is ..."), synthesize a definition from
#          provided CONTEXT or the KB instead of returning the parrot.
#
# Upstream:
#   - ENV (required): OPENAI_API_KEY
#   - ENV (optional):
#       ECHO_MODEL         (default "gpt-4o-mini")
#       ECHO_MAX_TOKENS    (default 700)
#       ECHO_TEMPERATURE   (default 0.2)
#       ECHO_TIMEOUT_S     (default 45)
#       ECHO_MAX_RETRIES   (default 2)
#       ECHO_MAX_CHARS     (default 600)
#   - Imports: os, asyncio, typing, re, openai, utils.openai_client, core.logging
#
# Downstream:
#   - agents.mcp_agent (primary caller)
#   - routes.ask (indirectly via MCP)
#
# Contents:
#   - run(query, context="", user_id="anonymous", plan=None) -> dict
#   - stream(query, context="", user_id="anonymous") -> async generator

# File: agents/echo_agent.py
from __future__ import annotations
import re
from typing import Any, Dict, Optional

from core.logging import log_event
from services.kb import definition_from_kb  # keep optional if you stub in tests

PARROT_PAT = re.compile(r"^(understand|here is|definition of|it seems|you are asking|what is|define|describe)\b", re.I)

def _clean_text(s: Optional[str]) -> str:
    return (s or "").strip()

def _too_similar(q: str, a: str) -> bool:
    qw = set(w for w in re.findall(r"[a-z0-9]+", (q or "").lower()) if len(w) > 2)
    aw = set(w for w in re.findall(r"[a-z0-9]+", (a or "").lower()) if len(w) > 2)
    if not qw or not aw:
        return False
    return (len(qw & aw) / max(1, len(qw | aw))) > 0.80

def _synthesize_definition_from_context(query: str, context: str) -> str:
    # very light extract: first 2–4 “X is …” sentences from context
    # (replace with your richer extractor if you have one)
    sents = re.split(r"(?<=[.!?])\s+", context or "")
    pick = []
    for s in sents:
        ls = s.lower().strip()
        if " is a " in ls or " is an " in ls or ls.startswith("relay command center is"):
            pick.append(s.strip())
        if len(pick) >= 4:
            break
    return " ".join(pick[:4]).strip()

async def run(
    query: str,
    context: str,
    user_id: str = "anonymous",
    plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Echo respects planner, but NEVER returns a parrot.
    Origin ladder: planner → context → kb → llm (honest fallback).
    """
    # 1) Build initial candidate (planner FA if present, else empty)
    candidate = ""
    origin = None
    if isinstance(plan, dict) and isinstance(plan.get("final_answer"), str):
        fa = _clean_text(plan["final_answer"])
        if fa:
            candidate = fa
            origin = "planner"

    # If no planner FA, we can try a tiny LLM draft if you keep one; else leave empty
    # candidate, origin = llm_draft, "llm"  # (optional) if you do freeform generation here

    # 2) Anti-parrot gate on ANY candidate
    antiparrot = {"detected": False, "reason": ""}
    def looks_like_parrot(q: str, a: str) -> bool:
        return bool(PARROT_PAT.match((a or "").strip())) or _too_similar(q, a or "")

    if candidate and looks_like_parrot(query, candidate):
        antiparrot = {"detected": True, "reason": "pattern_or_similarity"}
        # try Context → KB
        synth = _synthesize_definition_from_context(query, context)
        if synth:
            candidate = _clean_text(synth)
            origin = "context"
            log_event("echo_antiparrot_synth_context", {"user": user_id, "chars": len(candidate)})
        else:
            kb_def = definition_from_kb(query) if definition_from_kb else None
            if kb_def:
                candidate = _clean_text(kb_def)
                origin = "kb"
                log_event("echo_antiparrot_synth_kb", {"user": user_id, "chars": len(candidate)})

    # 3) If we still have nothing or it still smells like a parrot, emit honest fallback
    if not candidate or looks_like_parrot(query, candidate):
        candidate = "I don’t have a clean definition from context. I can synthesize one from the KB or scan the repo—want me to do that?"
        origin = origin or "llm"
        if not antiparrot["detected"]:
            antiparrot = {"detected": True, "reason": "fallback"}

    # 4) Return with meta/provenance
    log_event("echo_agent_reply", {"user": user_id, "reply_head": candidate[:500], "origin": origin})
    return {
        "answer": candidate,
        "response": candidate,
        "route": "echo",
        "meta": {"origin": origin, "antiparrot": antiparrot},
    }
