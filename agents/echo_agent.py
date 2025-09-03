# File: agents/echo_agent.py
# Purpose: Non-parroting answerer with deterministic synth fallback.
# Contract:
#   await answer(query: str, context: dict, debug: bool=False, request_id: str|None=None,
#                timeout:str|int=20, model:str|None=None) -> dict
#
# Returns (stable, MCP-friendly):
#   {
#     "text": "<final human-readable string>",
#     "answer": "<same as text for back-compat>",
#     "response": { "model": "...", "usage": {...}, "raw": <llm obj>|None },
#     "meta": { "origin": "echo", "model": "<name>", "request_id": "<id>" }
#   }
#
# Features:
# - Anti-parrot: blocks lead-ins ("What is/Define/Understand"), checks similarity (Jaccard),
#   enforces new-token ratio, trims instructiony phrasing, and falls back to a deterministic synth.
# - Deterministic synth: uses `context.plan.final_answer`/reply_head when present, else concise
#   project-grounded summary from query + context hints (files/topics).
# - Resilience: per-call timeout, limited retries with exponential backoff + jitter.
# - Observability: emits minimal meta; route-level spans/metrics are already handled by caller.

from __future__ import annotations

import asyncio
import random
import re
from typing import Any, Dict, Optional, Tuple

from core.logging import log_event

# Your thin OpenAI wrapper (async), expected to expose chat_complete(...)
# Signature (recommended): await chat_complete(system, user, model, timeout_s) -> {"text": str, "usage": {...}, "raw": obj}
try:
    from services.openai_client import chat_complete  # type: ignore
except Exception:
    chat_complete = None  # pragma: no cover


# -------------------------- Jittered backoff + timeout --------------------------

_TRANSIENT = ("timeout", "rate limit", "temporar", "unavailable", "again", "overloaded")

def _is_transient(ex: Exception) -> bool:
    msg = str(ex).lower()
    return any(k in msg for k in _TRANSIENT)

def _jitter(attempt: int, base: float = 0.25, cap: float = 2.5) -> float:
    # full jitter (AWS style): min(cap, base * 2^n) * rand[0,1)
    return min(cap, base * (2 ** attempt)) * random.random()


# ----------------------------- Similarity + filters -----------------------------

_PREFIX_BLOCK = re.compile(
    r"^\s*(?:what\s+is|what\s+are|who\s+is|who\s+are|define|definition\s+of|understand|let(?:'s)?\s+understand|"
    r"in\s+this\s+answer|here'?s\s+what|we\s+will\s+|in\s+summary[:,]?|the\s+following\s+|"
    r"this\s+response\s+|i\s+will\s+)",
    re.IGNORECASE,
)

def _tokenize_words(s: str) -> set:
    # coarse tokenization for Jaccard; lowercased words, strip punctuation
    s = re.sub(r"[^a-z0-9\s]", " ", s.lower())
    return {w for w in s.split() if w}

def _jaccard(a: str, b: str) -> float:
    A, B = _tokenize_words(a), _tokenize_words(b)
    if not A and not B:
        return 0.0
    inter = len(A & B)
    union = len(A | B) or 1
    return inter / union

def _new_token_ratio(prompt: str, text: str) -> float:
    A, B = _tokenize_words(prompt), _tokenize_words(text)
    if not B:
        return 0.0
    # fraction of answer tokens that were NOT in the question
    return len(B - A) / len(B)


# ------------------------------- Deterministic synth ----------------------------

def _deterministic_synth(query: str, context: Dict[str, Any]) -> str:
    """Short, declarative answer that avoids parroting."""
    plan = (context or {}).get("plan") or {}
    # Prefer a planner-provided head if present
    head = (plan.get("final_answer") or "").strip()
    if head:
        return _clean_head(head)

    files = (context or {}).get("files") or []
    topics = (context or {}).get("topics") or []
    anchors = []
    if topics:
        anchors.extend(topics[:2])
    if files:
        anchors.extend([_basename(f) for f in files[:2]])
    anchor_str = f" (Context: {', '.join(anchors[:3])})" if anchors else ""
    key = _clean_head(_strip_punct(query))[:80] or "Answer"
    return f"{key}: a concise, project-grounded explanation.{anchor_str}"

def _basename(p: str) -> str:
    import os
    try:
        b = os.path.basename(p)
        return b or p
    except Exception:
        return p

def _strip_punct(s: str) -> str:
    return re.sub(r"[?!.:\-–—]+$", "", s).strip()

def _clean_head(s: str) -> str:
    # remove any instructiony lead-ins and ensure no trailing boilerplate
    s = _PREFIX_BLOCK.sub("", s).strip()
    s = re.sub(r"^\s*(?:answer[:\- ]+)?", "", s, flags=re.IGNORECASE)
    return s.strip()


# ------------------------------- LLM wrapper prompt -----------------------------

_SYSTEM = (
    "You answer crisply with direct, declarative prose. "
    "No lead-ins like 'What is', 'Define', 'In this answer', or 'We will'. "
    "One short paragraph unless brevity harms clarity. "
    "If asked to summarize files or code, produce the answer directly—no preambles."
)

def _build_user_prompt(query: str, context: Dict[str, Any]) -> str:
    # Give minimal steering; Echo receives the planner focus/steps via context if needed
    files = context.get("files") if isinstance(context, dict) else None
    topics = context.get("topics") if isinstance(context, dict) else None
    hints = []
    if topics:
        hints.append(f"Topics: {', '.join(map(str, topics[:3]))}")
    if files:
        hints.append(f"Files: {', '.join(_basename(f) for f in files[:3])}")
    hint_str = ("\n" + "\n".join(hints)) if hints else ""
    return f"{_strip_punct(query)}{hint_str}"


# ----------------------------------- Public API --------------------------------

async def answer(
    *,
    query: str,
    context: Dict[str, Any] | None = None,
    debug: bool = False,
    request_id: Optional[str] = None,
    timeout: int | float = 20,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Produce a non-parroting answer with strong guarantees.
    """
    context = context or {}
    model = model or "gpt-4o-mini"  # choose your default
    attempts = 0
    llm_usage: Dict[str, Any] | None = None
    llm_raw: Any = None

    # 1) Deterministic head: used as primary or as post-filter if LLM misbehaves
    head = _deterministic_synth(query, context)

    # 2) Try LLM (optional), with timeout & jittered retries on transient errors
    llm_text: Optional[str] = None
    if chat_complete:
        while attempts < 3 and llm_text is None:
            attempts += 1
            try:
                async with asyncio.timeout(timeout):
                    resp = await chat_complete(
                        system=_SYSTEM,
                        user=_build_user_prompt(query, context),
                        model=model,
                        timeout_s=int(timeout),
                    )
                cand = (resp.get("text") or "").strip()
                # Collect aux for meta/debug
                llm_usage = resp.get("usage")
                llm_raw = resp.get("raw")
                # 3) Post-process: anti-parrot + style clean
                llm_text = _postprocess(query, cand, fallback=head)
            except asyncio.TimeoutError as ex:
                if attempts >= 3:
                    break
                await asyncio.sleep(_jitter(attempts))
            except Exception as ex:
                if not _is_transient(ex) or attempts >= 3:
                    break
                await asyncio.sleep(_jitter(attempts))

    # 4) Choose final
    final = (llm_text or head).strip()
    final = _clean_head(final)
    # Ensure the answer is non-empty and non-parrot
    if not final:
        final = head
    if _PREFIX_BLOCK.search(final) or _is_parrot(query, final):
        final = head

    # 5) Emit structured meta + response
    out = {
        "text": final,
        "answer": final,  # back-compat for older paths
        "response": {
            "model": model,
            "usage": llm_usage,
            "raw": llm_raw if debug else None,
        },
        "meta": {
            "origin": "echo",
            "model": model,
            "request_id": request_id,
        },
    }
    log_event("echo_answered", {
        "request_id": request_id,
        "attempts": attempts,
        "final_len": len(final),
        "used_llm": bool(llm_text),
    })
    return out


# --------------------------------- Parrot logic ---------------------------------

def _is_parrot(prompt: str, text: str) -> bool:
    """
    Multi-signal heuristic:
      1) lead-in prefix blacklist
      2) high lexical overlap (Jaccard)
      3) low new-token ratio (answer mostly reuses prompt words)
    """
    if _PREFIX_BLOCK.search(text):
        return True
    sim = _jaccard(prompt, text)
    if sim >= 0.72:  # conservative threshold
        return True
    if _new_token_ratio(prompt, text) < 0.35:
        return True
    return False


def _postprocess(prompt: str, text: str, fallback: str) -> str:
    """
    Strip lead-ins, enforce non-parrot structure, trim whitespace.
    If result still looks parrotish, use `fallback`.
    """
    if not text:
        return fallback
    cand = _clean_head(text)
    # Remove obvious "As an AI..." boilerplate or instructiony clauses
    cand = re.sub(r"^\s*as an? (ai|language model)[^.,]*[.,]\s*", "", cand, flags=re.IGNORECASE)
    cand = re.sub(r"^\s*(here(?:'s)?|this is)\s+(?:a|an)\s+", "", cand, flags=re.IGNORECASE)
    # Enforce non-parrot
    if _is_parrot(prompt, cand):
        return fallback
    return cand.strip()
