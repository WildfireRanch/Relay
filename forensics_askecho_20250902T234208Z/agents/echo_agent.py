# File: agents/echo_agent.py
# Purpose: Final answer synthesis for /ask. Prefer concise, answer-first replies.
#          Honors Planner fast-path via plan.final_answer. If the candidate looks
#          parrotish, synthesize from CONTEXT (deterministic) or KB. Returns a
#          shape MCP can normalize easily (uses "text" field).
#
# Upstream:
#   ENV (optional):
#     ECHO_MAX_CHARS      (default "600")   # max characters for the final answer
#
# Downstream compatibility:
#   - MCP normalizer extracts strings from {"text": "..."} automatically.
#   - Legacy fields ("answer") are kept to avoid breaking old callers.
#
# Notes:
#   - No extra LLM calls here: deterministic + KB lookups only.
#   - Logs a concise reply head for observability.

from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional

from core.logging import log_event
try:
    # Optional: not required for runtime; guard for tests/minimal envs
    from services.kb import definition_from_kb  # type: ignore
except Exception:  # pragma: no cover
    definition_from_kb = None  # type: ignore

MAX_CHARS = int(os.getenv("ECHO_MAX_CHARS", "600"))

# --------------------------------------------------------------------------- #
# Parrot detection                                                            #
# --------------------------------------------------------------------------- #

_PARROT_HEAD = re.compile(
    r"^(understand|here is|definition of|it seems|you are asking|"
    r"what is|who is|define|describe|explain)\b",
    re.I,
)

_WORDS = re.compile(r"[a-z0-9]+", re.I)
_SENTENCES = re.compile(r"(?<=[.!?])\s+")
# Accept definitions phrased as:
#   "X is a/an ...", "X— a/an ...", "X: a/an ...", "X, a/an ..."
_DEF_LIKE = [
    re.compile(r"\bis\s+a\b", re.I),
    re.compile(r"\bis\s+an\b", re.I),
    re.compile(r"\b[:\-–—]\s*(a|an)\s+\b", re.I),
    re.compile(r"\b,\s*(a|an)\s+\b", re.I),
]

_STOPWORDS = {
    "what", "who", "is", "the", "a", "an", "define", "describe", "explain",
    "of", "in", "for", "to", "on", "and", "or", "with", "about",
}

def _clean(s: Optional[str]) -> str:
    return (s or "").strip()

def _too_similar(q: str, a: str) -> bool:
    qw = {w for w in _WORDS.findall((q or "").lower()) if len(w) > 2}
    aw = {w for w in _WORDS.findall((a or "").lower()) if len(w) > 2}
    if not qw or not aw:
        return False
    jaccard = len(qw & aw) / max(1, len(qw | aw))
    return jaccard > 0.80

def _new_token_count(q: str, a: str) -> int:
    qw = set(_WORDS.findall((q or "").lower()))
    aw = set(_WORDS.findall((a or "").lower()))
    return sum(1 for t in (aw - qw) if len(t) > 3)

def _looks_like_parrot(q: str, a: str) -> bool:
    a = _clean(a)
    if not a:
        return True
    return bool(_PARROT_HEAD.match(a)) or _too_similar(q, a) or _new_token_count(q, a) < 2

def _is_def_like(s: str) -> bool:
    ls = s.lower()
    if _PARROT_HEAD.match(ls):
        return False
    return any(p.search(ls) for p in _DEF_LIKE)

# --------------------------------------------------------------------------- #
# Deterministic synthesis from context                                        #
# --------------------------------------------------------------------------- #

def _key_from_query(query: str) -> str:
    toks = [t for t in _WORDS.findall((query or "").lower()) if t not in _STOPWORDS]
    # entity signal is usually in the tail; keep last 3 content tokens
    return " ".join(toks[-3:]) if toks else ""

def _pack_def_sentences(context: str, key: str, max_sentences: int = 4) -> str:
    """
    Pick up to 2–4 definition-like sentences from context, preferring ones that
    mention the key phrase. No tokenizers; fast and deterministic.
    """
    sents = [s.strip() for s in _SENTENCES.split(context or "") if s.strip()]
    if not sents:
        return ""
    picks = []

    # 1) Prefer sentences that are def-like AND contain the key
    if key:
        for s in sents:
            if key in s.lower() and _is_def_like(s):
                picks.append(s)
                if len(picks) >= max_sentences:
                    break

    # 2) Fill with def-like sentences even if they don't contain the key
    if len(picks) < max_sentences:
        for s in sents:
            if s in picks:
                continue
            if _is_def_like(s):
                picks.append(s)
                if len(picks) >= max_sentences:
                    break

    # 3) As a last resort, take the first couple of sentences
    if not picks:
        picks = sents[:max_sentences]

    out = " ".join(picks[:max_sentences]).strip()
    if len(out) > MAX_CHARS:
        out = out[:MAX_CHARS].rstrip() + "…"
    return out

# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #

async def run(
    query: str,
    context: str,
    user_id: str = "anonymous",
    plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Echo respects planner, but NEVER returns a parrot.
    Origin ladder: planner → context → kb → fallback note.
    Returns a dict with "text" so MCP can normalize the answer string.
    """
    # 1) Candidate from planner (if any)
    candidate = ""
    origin = None
    if isinstance(plan, dict) and isinstance(plan.get("final_answer"), str):
        candidate = _clean(plan["final_answer"])
        origin = "planner"

    antiparrot = {"detected": False, "reason": ""}

    # 2) Parrot gate for ANY candidate (including planner FA)
    if candidate and _looks_like_parrot(query, candidate):
        antiparrot = {"detected": True, "reason": "pattern_similarity_newtoken"}
        candidate = ""  # clear so we try synth routes

    # 3) Deterministic synth from CONTEXT if needed
    if not candidate:
        key = _key_from_query(query)
        synth = _pack_def_sentences(context or "", key)
        if synth and not _looks_like_parrot(query, synth):
            candidate = _clean(synth)
            origin = "context"
            log_event("echo_antiparrot_synth_context", {"user": user_id, "chars": len(candidate)})

    # 4) Optional KB fallback
    if not candidate and definition_from_kb:
        try:
            kb_def = definition_from_kb(query)  # type: ignore
        except Exception:
            kb_def = None
        if isinstance(kb_def, str) and kb_def.strip() and not _looks_like_parrot(query, kb_def):
            candidate = _clean(kb_def)
            origin = "kb"
            log_event("echo_antiparrot_synth_kb", {"user": user_id, "chars": len(candidate)})

    # 5) Honest user-facing fallback (concise)
    if not candidate:
        candidate = (
            "I don’t have a clean, context-based definition yet. "
            "I can synthesize one from the KB or scan the repo—should I do that?"
        )
        origin = origin or "fallback"
        if not antiparrot["detected"]:
            antiparrot = {"detected": True, "reason": "fallback"}

    # Cap one last time
    if len(candidate) > MAX_CHARS:
        candidate = candidate[:MAX_CHARS].rstrip() + "…"

    # Observability
    log_event("echo_agent_reply", {"user": user_id, "origin": origin, "reply_head": candidate[:500]})

    # Return a shape that MCP can normalize (prefers "text")
    payload: Dict[str, Any] = {
        "text": candidate,                   # <-- MCP _best_string will pick this up
        "answer": candidate,                 # legacy field (kept for compatibility)
        "route": "echo",
        "meta": {
            "origin": origin,
            "antiparrot": antiparrot,
        },
    }
    return payload


# Optional streaming façade (simple: one-chunk stream for now)
async def stream(
    query: str,
    context: str,
    user_id: str = "anonymous",
    plan: Optional[Dict[str, Any]] = None,
):
    """
    Minimal async generator for compatibility with code paths expecting streams.
    Emits a single chunk (no LLM here), then completes.
    """
    result = await run(query=query, context=context, user_id=user_id, plan=plan)
    yield {"text": result.get("text", ""), "meta": result.get("meta", {})}
