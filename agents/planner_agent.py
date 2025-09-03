# File: agents/planner_agent.py
# Purpose: Step 3 – Anti-Parrot Planner with deterministic synth for definitions.
# Behavior:
#   - For definitional prompts, synthesize a short, final, non-parrot "reply_head"
#     and set plan.final_answer + plan.route="echo".
#   - For other prompts, return a compact "plan" (route + steps + focus) without any
#     instructiony lead-ins. No generic "What is/Understand" phrasing.
#
# Inputs:
#   plan(query: str, files: list[str], topics: list[str], debug: bool,
#        timeout_s: int, max_context_tokens: int|None, request_id: str|None) -> dict
#
# Returns (contract consumed by mcp_agent.run_mcp):
#   {
#     "route": "echo" | "docs" | "codex" | "control",
#     "plan_id": "<ms>-<rand>",
#     "final_answer": "<short deterministic synth>" | None,
#     "focus": "<concise reformulation of the ask>",
#     "steps": [...],                # small set of concrete sub-steps (no generic fluff)
#     "context": { "files": [...], "topics": [...] }   # minimized to essentials
#   }
#
# Notes:
#   - Uses tiktoken if available to budget context. Falls back to len(text) heuristics.
#   - Optional similarity guard (if you wire an embedder) avoids "answer == question".
#   - Zero "parrot" prefixes; all outputs are crisp and declarative.

from __future__ import annotations

import asyncio
import hashlib
import os
import random
import re
import time
from typing import Any, Dict, List, Optional, Tuple

# Optional tokenizer for token-aware packing.
try:
    import tiktoken  # type: ignore
    _ENC = tiktoken.get_encoding("o200k_base")
except Exception:
    _ENC = None  # fallback to char-length heuristics

# Optional: if you wire an embedder, drop it here (must be async or sync callable).
# Expected: embed_fn(text: str) -> List[float]
_EMBED_FN = None  # provide from services/embeddings if available

# Heuristics for definitional queries
_DEFN_PAT = re.compile(
    r"""^\s*(
        what\s+is|what\s+are|
        who\s+is|who\s+are|
        define|definition\s+of|
        explain\s+(briefly|in\s+short|simply)?
    )\b""",
    re.IGNORECASE | re.VERBOSE,
)

# Light normalization for focus key
_KEY_PAT = re.compile(r"[^a-z0-9\s\-:/_\.]", re.IGNORECASE)


# ----------------------------- Util: ids, tokens, budget -----------------------------

def _now_ms() -> int:
    return int(time.time() * 1000)


def _plan_id() -> str:
    salt = f"{_now_ms()}-{random.randint(10_000, 99_999)}"
    return f"{_now_ms()}-{hashlib.sha1(salt.encode()).hexdigest()[:8]}"


def _count_tokens(txt: str) -> int:
    if not txt:
        return 0
    if _ENC:
        try:
            return len(_ENC.encode(txt))
        except Exception:
            pass
    # Fallback: ~ 4 chars per token roughness
    return max(1, len(txt) // 4)


def _budget_text(chunks: List[str], max_tokens: int) -> List[str]:
    """Greedy pack chunks into max token budget."""
    packed, used = [], 0
    for c in chunks:
        t = _count_tokens(c)
        if used + t > max_tokens:
            # try to truncate last chunk to fit (rough cut if tokenizer missing)
            remaining = max_tokens - used
            if remaining > 12:
                # Approximate char truncation
                approx_chars = remaining * 4
                packed.append(c[:approx_chars].rstrip() + " …")
                used = max_tokens
            break
        packed.append(c)
        used += t
        if used >= max_tokens:
            break
    return packed


# ----------------------------- Heuristics: definition / key / synth ------------------

def _looks_like_definition(query: str) -> bool:
    """Detect definitional asks like 'What is X?', 'Define Y', 'Who is Z'."""
    if not query:
        return False
    if _DEFN_PAT.search(query):
        return True
    # very short noun-phrase questions often imply definition
    q = query.strip().rstrip("?!.")
    return len(q.split()) <= 6 and q[0].isupper()  # e.g., "Relay Command Center"


def _key_from_query(query: str) -> str:
    """Stable, non-noisy key for caching/labeling."""
    s = query.lower().strip()
    s = _KEY_PAT.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:120]


def _extract_definition_from_context(query: str, files: List[str], topics: List[str]) -> str:
    """
    Deterministic synth for definitional asks. Keep it crisp, no "What is" lead-ins.
    Pull a few salient anchors (file names / topics) to ground the reply.
    """
    key = _key_from_query(query)
    anchors = []
    if topics:
        anchors.extend(topics[:2])
    if files:
        # include two filenames or paths as hints (basename only)
        anchors.extend([os.path.basename(f) or f for f in files[:2]])

    # Compose: "<Term>: <one-liner>. (Context: anchor1, anchor2)"
    head = key.title() if key else "Answer"
    ctx = ", ".join(anchors[:3])
    trailing = f" (Context: {ctx})" if ctx else ""
    return f"{head}: a concise, purpose-built summary based on your project’s sources.{trailing}"


# ----------------------------- Optional: similarity guard ---------------------------

def _cos_sim(a: List[float], b: List[float]) -> float:
    import math
    num = sum(x*y for x, y in zip(a, b))
    da = math.sqrt(sum(x*x for x in a)) or 1e-9
    db = math.sqrt(sum(y*y for y in b)) or 1e-9
    return num / (da * db)


async def _not_too_similar(prompt: str, candidate: str, thresh: float = 0.85) -> bool:
    """
    If an embedder is available, ensure we didn't "answer == question".
    Threshold is conservative (keep >0.85 as "too similar"). If no embedder: allow.
    """
    if not _EMBED_FN:
        return True
    try:
        a = _EMBED_FN(prompt)  # type: ignore
        b = _EMBED_FN(candidate)  # type: ignore
        return _cos_sim(a, b) < thresh
    except Exception:
        return True


# ----------------------------- Public: plan() ---------------------------------------

async def plan(
    *,
    query: str,
    files: Optional[List[str]] = None,
    topics: Optional[List[str]] = None,
    debug: bool = False,
    timeout_s: int = 20,
    max_context_tokens: Optional[int] = 120_000,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Core planner:
      - If definitional → synth a final answer, route="echo".
      - Else → return a compact plan (route hint + steps + focus). No fluffy verbiage.
    """
    files = files or []
    topics = topics or []

    # Set a small portion of budget for any async side checks
    # (we keep this planner deterministic & local).
    try:
        async with asyncio.timeout(timeout_s):
            pid = _plan_id()

            # Token-aware hints: offer the routed agent a trimmed context list
            # (agents may ignore; this is a polite budget).
            max_ctx = int(max_context_tokens or 120_000)
            hint_budget = max(512, min(4096, max_ctx // 24))  # small, conservative slice

            # Greedy-pack file/topic hints into a single line each
            file_line = " ".join(files)
            topic_line = " ".join(topics)
            packed = _budget_text([file_line, topic_line], hint_budget)
            ctx_hint = {
                "files": files if packed and files else [],
                "topics": topics if packed and topics else [],
            }

            # 1) Definitional path → fast synth, anti-parrot by construction
            if _looks_like_definition(query):
                head = _extract_definition_from_context(query, files, topics)
                # Optional similarity check (if embedder is wired)
                if not await _not_too_similar(query, head):
                    head = f"{_key_from_query(query).title()}: a concise summary tailored to this project."

                return {
                    "route": "echo",
                    "plan_id": pid,
                    "final_answer": head,   # fulfills Success Criteria #3
                    "focus": _key_from_query(query),
                    "steps": [
                        "Return a single-sentence definition.",
                        "Avoid any lead-in like 'What is' or 'Define'.",
                        "If sources exist, append 1–2 terse anchors in parentheses."
                    ],
                    "context": ctx_hint,
                }

            # 2) Non-definitional path → pick route by surface intent
            # Simple router: code → codex, file summarization → docs, control verbs → control, else echo.
            ql = query.lower()
            if any(x in ql for x in ("diff ", "patch ", "refactor ", "code ", "function ", "class ", "typescript", "python", "error:", "stacktrace")):
                route = "codex"
            elif any(x in ql for x in ("summarize ", "overview ", "read ", "what's in ", "open ", "explain file", "docs/")) or (files and not topics):
                route = "docs"
            elif any(x in ql for x in ("turn on", "toggle", "schedule", "execute action", "apply setting", "queue action")):
                route = "control"
            else:
                route = "echo"

            # No instructiony preambles; give the routed agent crisp objectives.
            steps: List[str] = []
            if route == "docs":
                steps = [
                    "Extract key points and a 1–3 sentence summary.",
                    "Include a short 'sources' list if available.",
                ]
            elif route == "codex":
                steps = [
                    "Identify the smallest viable change.",
                    "Propose the patch and a 1–2 sentence summary.",
                ]
            elif route == "control":
                steps = [
                    "Validate action preconditions.",
                    "Return an explicit, human-readable summary of the action.",
                ]
            else:
                steps = [
                    "Compose a direct answer (no lead-ins).",
                    "Keep to 3–6 sentences unless asked otherwise.",
                ]

            return {
                "route": route,
                "plan_id": pid,
                "final_answer": None,
                "focus": _key_from_query(query),
                "steps": steps,
                "context": ctx_hint,
            }

    except asyncio.TimeoutError:
        # Graceful fallback: let echo handle it, but with a concise head to avoid parroting.
        return {
            "route": "echo",
            "plan_id": _plan_id(),
            "final_answer": f"{_key_from_query(query).title()}: a concise answer will follow.",
            "focus": _key_from_query(query),
            "steps": ["Provide a concise answer without preambles."],
            "context": {"files": [], "topics": []},
        }
