# ──────────────────────────────────────────────────────────────────────────────
# File: agents/planner_agent.py
# Purpose: Anti-parrot planner with definitional fast-path. Exposes a **sync**
#          plan() that tolerates extra kwargs (e.g., corr_id) and keeps
#          behavior intact. Internals may remain async; the public API is sync.
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Dict, List, Optional

# Lightweight logging
try:
    from core.logging import log_event  # type: ignore
except Exception:  # pragma: no cover
    def log_event(event: str, data: Optional[Dict[str, Any]] = None) -> None:
        pass

# ---- internal helpers (unchanged behavior) -----------------------------------

def _plan_id() -> str:
    return f"{int(time.time()*1000)}-{random.randint(1000, 9999)}"

def _key_from_query(q: str) -> str:
    q = (q or "").strip()
    return (q[:60] or "query").lower()

def _looks_definitional(q: str) -> bool:
    q = (q or "").strip().lower()
    heads = ("what is", "define", "explain", "who is", "tell me what", "understand", "summarize")
    return any(q.startswith(h) for h in heads) or len(q.split()) <= 4

async def _plan_core(
    *,
    query: str,
    files: Optional[List[str]] = None,
    topics: Optional[List[str]] = None,
    debug: bool = False,
    timeout_s: int = 20,
    max_context_tokens: Optional[int] = 120_000,
    request_id: Optional[str] = None,
    **_: Any,
) -> Dict[str, Any]:
    """Original async core. Keep logic deterministic and local."""
    files = files or []
    topics = topics or []

    try:
        if _looks_definitional(query):
            head = f"{_key_from_query(query).title()}: a concise answer will follow."
            out = {
                "route": "echo",
                "plan_id": _plan_id(),
                "final_answer": head,
                "focus": _key_from_query(query),
                "steps": ["Provide a concise answer without preambles."],
                "context": {"files": files, "topics": topics},
                "_diag": {"definitional": True},
            }
            return out

        # Non-definitional: compact plan
        steps = ["Answer concisely, avoid parroting.", "Use retrieved context if present."]
        ctx_hint = {"files": files[:6], "topics": topics[:6]}
        return {
            "route": "echo",
            "plan_id": _plan_id(),
            "focus": _key_from_query(query),
            "steps": steps,
            "context": ctx_hint,
            "_diag": {"definitional": False},
        }
    except asyncio.TimeoutError:
        return {
            "route": "echo",
            "plan_id": _plan_id(),
            "final_answer": f"{_key_from_query(query).title()}: a concise answer will follow.",
            "focus": _key_from_query(query),
            "steps": ["Provide a concise answer without preambles."],
            "context": {"files": [], "topics": []},
            "_diag": {"timeout": True},
        }

# ---- public API (sync; tolerant to extra kwargs) -----------------------------

def plan(
    *,
    query: str,
    files: Optional[List[str]] = None,
    topics: Optional[List[str]] = None,
    debug: bool = False,
    timeout_s: int = 20,
    max_context_tokens: Optional[int] = 120_000,
    request_id: Optional[str] = None,
    corr_id: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    # keep behavior, ignore unknown kwargs
    files = files or []
    topics = topics or []
    rid = request_id or corr_id
    cid = corr_id or request_id

    try:
        if _looks_definitional(query):
            head = f"{_key_from_query(query).title()}: a concise answer will follow."
            out = {
                "route": "echo",
                "plan_id": _plan_id(),
                "final_answer": head,
                "focus": _key_from_query(query),
                "steps": ["Provide a concise answer without preambles."],
                "context": {"files": files[:6], "topics": topics[:6]},
                "_diag": {"definitional": True},
            }
            return out

        steps = ["Answer concisely, avoid parroting.", "Use retrieved context if present."]
        ctx_hint = {"files": files[:6], "topics": topics[:6]}
        return {
            "route": "echo",
            "plan_id": _plan_id(),
            "focus": _key_from_query(query),
            "steps": steps,
            "context": ctx_hint,
            "_diag": {"definitional": False},
        }

    except Exception as e:
        log_event(
            "planner_error",
            {"error": str(e or ""), "request_id": rid, "corr_id": cid},
        )
        return {
            "route": "echo",
            "plan_id": _plan_id(),
            "final_answer": f"{_key_from_query(query).title()}: a concise answer will follow.",
            "focus": _key_from_query(query),
            "steps": ["Provide a concise answer without preambles."],
            "context": {"files": [], "topics": []},
            "_diag": {"error": True, "msg": str(e or "")},
        }
