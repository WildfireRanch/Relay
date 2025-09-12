# ──────────────────────────────────────────────────────────────────────────────
# Directory : agents
# File      : planner_agent.py
# Purpose   : Deterministic planner; accepts corr_id and ignores unknown kwargs to prevent TypeError.
# Contracts : plan(query, files?, topics?, debug?, timeout_s?, corr_id?, max_context_tokens?, **kwargs) -> dict
# Guardrails: No circular deps; lightweight; stable keys consumed by mcp_agent.
# Notes     : - This module does NOT import from routes/* or main to avoid cycles.
#             - Designed to be JSON-safe and tolerant to Pydantic v1/v2 differences.
#             - GitHub/Relay read-only access for repo introspection is available via:
#                 GET /integrations/github/tree?owner=WildfireRanch&repo=Relay&ref=main&path=...
#                 GET /integrations/github/contents?owner=WildfireRanch&repo=Relay&ref=main&path=<FULL_PATH>
# ──────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
from typing import Any, Dict, Optional, List, Tuple, Callable
import inspect
import time

# ── Small, local utilities (no third‑party deps) ──────────────────────────────

def _now_ms() -> int:
    """Return current time in milliseconds (int)."""
    return int(time.time() * 1000)

def _filter_kwargs_for(func: Callable, data: Dict[str, Any]) -> Dict[str, Any]:
    """Return only kwargs accepted by *func*'s signature (by name).
    Prevents TypeError when upstream passes extras like corr_id, etc.
    """
    try:
        sig = inspect.signature(func)
        names = {p.name for p in sig.parameters.values()}
        return {k: v for k, v in (data or {}).items() if k in names}
    except Exception:
        # Fail-open: if inspect fails, return empty to avoid raising.
        return {}

def _nullsafe_merge_meta(meta: Optional[Dict[str, Any]], extra: Dict[str, Any]) -> Dict[str, Any]:
    """Merge meta dicts safely, ensuring kb stats and timings exist and are numeric.
    Keys ensured:
      meta.kb.{hits:int, max_score:float, sources:list[str]}
      meta.timings_ms.{planner_ms, context_ms, dispatch_ms, total_ms}: int
    """
    base = dict(meta or {})
    kb = dict(base.get("kb") or {})
    timings = dict(base.get("timings_ms") or {})
    # Normalize KB
    kb["hits"] = int(kb.get("hits") or 0)
    kb["max_score"] = float(kb.get("max_score") or 0.0)
    kb["sources"] = list(kb.get("sources") or [])
    # Normalize timings
    for k in ("planner_ms", "context_ms", "dispatch_ms", "total_ms"):
        v = timings.get(k)
        timings[k] = int(v) if isinstance(v, (int, float)) else 0
    base["kb"] = kb
    base["timings_ms"] = timings
    # Merge extras
    for k, v in (extra or {}).items():
        if k == "kb":
            ekb = dict(v or {})
            if "hits" in ekb: kb["hits"] = int(ekb.get("hits") or kb["hits"] or 0)
            if "max_score" in ekb: kb["max_score"] = float(ekb.get("max_score") or kb["max_score"] or 0.0)
            if "sources" in ekb:
                try:
                    exist = set(map(str, kb.get("sources") or []))
                    add = [str(s) for s in (ekb.get("sources") or [])]
                    kb["sources"] = list(exist.union(add))
                except Exception:
                    pass
        elif k == "timings_ms":
            for tk, tv in (v or {}).items():
                try:
                    timings[tk] = int(tv) if not isinstance(tv, bool) else timings.get(tk, 0)
                except Exception:
                    continue
        else:
            base[k] = v
    return base
from typing import Any, Dict, List, Optional
import asyncio
import random

DEFAULT_TIMEOUT_S = 45

def _plan_id() -> str:
    """Unique (coarse) plan id for traceability; safe for logs/metrics."""
    return f"{_now_ms()}-{random.randint(1000, 9999)}"

async def _plan_async(query: str,
                      files: Optional[List[str]] = None,
                      topics: Optional[List[str]] = None,
                      debug: bool = False,
                      timeout_s: int = DEFAULT_TIMEOUT_S,
                      corr_id: Optional[str] = None) -> Dict[str, Any]:
    """Core deterministic planner.
    - For definition-style prompts, your upstream may set route="echo" and synth later.
    - We keep this minimal & predictable; downstream agents perform the real work.
    """
    files = files or []
    topics = topics or []
    steps = [
        {"op": "answer", "focus": (query or "").strip()[:256]}
    ]
    return {
        "route": "echo",
        "plan_id": _plan_id(),
        "steps": steps,
        "focus": topics[:5],
        "_diag": {"debug": bool(debug), "files": len(files)},
    }

def plan(query: str,
         files: Optional[List[str]] = None,
         topics: Optional[List[str]] = None,
         debug: bool = False,
         timeout_s: int = DEFAULT_TIMEOUT_S,
         corr_id: Optional[str] = None,
         max_context_tokens: Optional[int] = None,
         **kwargs: Any) -> Dict[str, Any]:
    """Public entry; **kwargs tolerated so upstream can pass extra fields safely."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(_plan_async(
        query=query, files=files, topics=topics, debug=debug, timeout_s=timeout_s, corr_id=corr_id
    ))
