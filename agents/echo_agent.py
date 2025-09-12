# ──────────────────────────────────────────────────────────────────────────────
# Directory : agents
# File      : echo_agent.py
# Purpose   : Non-parroting answerer; adds invoke() shim for SAFE-MODE fallback to deterministic synth.
# Contracts : invoke(query, context?, debug?, corr_id?, **kwargs) -> dict; may call existing async answer() if present
# Guardrails: Never raises; returns text/answer/response/meta; no route/main imports.
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
from typing import Any, Dict, Optional

def _synth_local(query: str, context: Optional[Dict[str, Any]] = None) -> str:
    """Deterministic local synthesis used when the LLM path is unavailable.
    Trims common lead-ins to avoid parrot-y phrasing.
    """
    ctx_note = ""
    if isinstance(context, dict):
        title = context.get("title") or context.get("topic") or ""
        if title:
            ctx_note = f" (context: {str(title)[:80]})"
    q = (query or "").strip()
    if not q:
        return "No question provided."
    lowers = q.lower()
    for lead in ("what is ", "understand ", "define "):
        if lowers.startswith(lead):
            q = q[len(lead):]
            break
    return f"{q}{ctx_note}".strip()

def _format_response(text: str, model: str = "safe-local", request_id: Optional[str] = None) -> Dict[str, Any]:
    """Return the stable response envelope expected by /mcp → /ask."""
    return {
        "text": text,
        "answer": text,
        "response": {"model": model, "usage": {"total_tokens": 0}, "raw": None},
        "meta": {"origin": "echo", "model": model, "request_id": request_id},
    }

def invoke(query: str,
           context: Optional[Dict[str, Any]] = None,
           debug: bool = False,
           corr_id: Optional[str] = None,
           **kwargs: Any) -> Dict[str, Any]:
    """Safe entry. If async answer() exists, call it (sync/async tolerant).
    Otherwise return deterministic synth. Ensures meta.request_id.
    """
    try:
        ans_fn = globals().get("answer")
        if callable(ans_fn):
            payload = _filter_kwargs_for(ans_fn, {
                "query": query, "context": context, "debug": debug, "request_id": corr_id, **kwargs
            })
            out = ans_fn(**payload)
            if hasattr(out, "__await__"):
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                out = loop.run_until_complete(out)
            if isinstance(out, dict) and ("text" in out or "answer" in out):
                meta = dict(out.get("meta") or {})
                meta["request_id"] = meta.get("request_id") or corr_id
                out["meta"] = meta
                return out
    except Exception:
        # fall through
        pass
    return _format_response(_synth_local(query, context), request_id=corr_id)
