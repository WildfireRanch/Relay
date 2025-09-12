# ──────────────────────────────────────────────────────────────────────────────
# Directory : agents
# File      : mcp_agent.py
# Purpose   : Plan → build context → dispatch. Kwarg-filtering, ContextEngine adoption, null-safe meta.
# Contracts : run_mcp(query, files?, topics?, debug?, corr_id?, **kwargs) -> dict (never raises)
# Guardrails: No route/main imports; uses lazy imports; SAFE-MODE on failures.
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

# ── Local SAFE-MODE synthesizer (no external deps) ─────────────────────────────
from typing import Optional, Dict, Any

def _synth_local(query: str, context: Optional[Dict[str, Any]] = None) -> str:
    """
    Deterministic, dependency-free fallback used when echo/invoke is unavailable.
    Mirrors echo_agent's behavior lightly (no model usage, no tokens).
    """
    q = (query or "").strip()
    if not q:
        q = "No question provided."
    title = ""
    if isinstance(context, dict):
        title = str(context.get("title") or context.get("topic") or "").strip()
    return f"{q} (context: {title})" if title else q


# ── Lazy import helpers (avoid cycles) ────────────────────────────────────────
def _lazy_planner():
    try:
        from agents.planner_agent import plan  # type: ignore
        return plan
    except Exception:
        return None

def _lazy_echo():
    try:
        from agents.echo_agent import invoke  # type: ignore
        return invoke
    except Exception:
        return None

def _lazy_retriever():
    try:
        from services.semantic_retriever import TieredSemanticRetriever  # type: ignore
        return TieredSemanticRetriever
    except Exception:
        return None

def _lazy_ctx_engine():
    try:
        from core.context_engine import ContextRequest, EngineConfig, build_context, RetrievalTier  # type: ignore
        return ContextRequest, EngineConfig, build_context, RetrievalTier
    except Exception:
        # RetrievalTier may not exist in older builds; return Nones and we fallback.
        return None, None, None, None

# ── Public API ────────────────────────────────────────────────────────────────
def run_mcp(query: str,
            files: Optional[List[str]] = None,
            topics: Optional[List[str]] = None,
            debug: bool = False,
            corr_id: Optional[str] = None,
            **kwargs: Any) -> Dict[str, Any]:
    """End-to-end pipeline. Never raises; returns stable dict consumed by routes/ask.
    Shape:
      {
        "plan": {...},
        "routed_result": dict|str,
        "critics": list|None,
        "context": str,
        "files_used": list[dict{path, tier, score?}],
        "meta": { request_id, route, kb{hits,max_score,sources}, timings_ms{...} }
      }
    """
    t0 = _now_ms()

    # 1) PLAN
    plan_fn = _lazy_planner()
    planner_start = _now_ms()
    plan_out: Dict[str, Any] = {}
    if callable(plan_fn):
        payload = _filter_kwargs_for(plan_fn, {
            "query": query, "files": files, "topics": topics,
            "debug": debug, "timeout_s": 45, "corr_id": corr_id
        })
        try:
            plan_out = plan_fn(**payload) or {}
        except Exception as e:
            plan_out = {"route": "echo", "_diag": {"planner_error": str(e)}}
    else:
        plan_out = {"route": "echo", "_diag": {"planner_missing": True}}
    planner_ms = _now_ms() - planner_start
    route = str(plan_out.get("route") or "echo")

    # 2) CONTEXT (ContextEngine preferred; retriever fallback)
    Retriever = _lazy_retriever()
    ContextRequest, EngineConfig, build_context, RetrievalTier = _lazy_ctx_engine()

    kb_hits = 0
    kb_max = 0.0
    sources: List[str] = []
    context_md = ""
    context_ms = 0

    ctx_t0 = _now_ms()
    try:
        if ContextRequest and EngineConfig and build_context:
            # Prefer enum if present; else allow string keys transparently.
            try:
                tiers = {
                    RetrievalTier.GLOBAL:        Retriever("global"),
                    RetrievalTier.PROJECT_DOCS:  Retriever("project_docs"),
                } if (Retriever and RetrievalTier) else {}
            except Exception:
                tiers = {}

            if not tiers and Retriever:
                # Fallback to string-tier map for builds w/o RetrievalTier
                tiers = {"global": Retriever("global"), "project_docs": Retriever("project_docs")}

            if tiers:
                cfg = EngineConfig(retrievers=tiers)  # type: ignore[arg-type]
                req = ContextRequest(query=query, corr_id=corr_id)
                ctx = build_context(req, cfg)  # type: ignore[misc]
                # Normalize ContextResult
                context_md = str((ctx or {}).get("context") or "")
                files_used_list = list((ctx or {}).get("files_used") or [])
                matches = list((ctx or {}).get("matches") or [])
                # kb stats
                kb_hits = len(matches)
                try:
                    kb_max = max([float(m.get("score") or 0.0) for m in matches]) if matches else 0.0
                except Exception:
                    kb_max = 0.0
                sources = [str(p) for p in files_used_list]
        elif Retriever:
            # Manual context build (two-tier)
            global_r = Retriever("global")
            proj_r = Retriever("project_docs")
            g_hits = global_r.search(query, k=4)
            p_hits = proj_r.search(query, k=6)

            def consume(rows):
                nonlocal kb_hits, kb_max, sources, context_md
                buf = []
                for path, score, snippet in (rows or []):
                    sources.append(str(path))
                    kb_hits += 1
                    try:
                        kb_max = max(kb_max, float(score))
                    except Exception:
                        pass
                    buf.append(f"- {path} (score {float(score):.3f})\n\n{str(snippet or '')[:500]}\n")
                return "\n".join(buf)

            parts = []
            parts.append(consume(g_hits))
            parts.append(consume(p_hits))
            context_md = "\n".join([p for p in parts if p]).strip()
    except Exception:
        # Context build failure is non-fatal
        pass
    context_ms = _now_ms() - ctx_t0

    # 3) DISPATCH
    echo_fn = _lazy_echo()
    dispatch_t0 = _now_ms()
    routed_result: Dict[str, Any] | str = {}
    if route == "echo" and callable(echo_fn):
        try:
            payload = _filter_kwargs_for(echo_fn, {
                "query": query,
                "context": {"markdown": context_md},
                "debug": debug,
                "corr_id": corr_id
            })
            routed_result = echo_fn(**payload)
        except Exception as e:
            routed_result = {"text": _synth_local(query, {"title": "SAFE MODE"}), "error": str(e)}
    else:
        # Unknown/unimplemented route → SAFE echo
        routed_result = {"text": _synth_local(query, {"title": "SAFE MODE"})}
    dispatch_ms = _now_ms() - dispatch_t0

    total_ms = _now_ms() - t0
    meta = _nullsafe_merge_meta({
        "request_id": corr_id,
        "route": route,
    }, {
        "kb": {"hits": kb_hits, "max_score": kb_max, "sources": sources},
        "timings_ms": {
            "planner_ms": planner_ms,
            "context_ms": context_ms,
            "dispatch_ms": dispatch_ms,
            "total_ms": total_ms
        },
    })

    files_used = [{"path": s, "tier": ("global" if "/global/" in s else "project_docs")} for s in sources]

    return {
        "plan": plan_out,
        "routed_result": routed_result,
        "critics": None,   # reserved for future critics integration
        "context": context_md,
        "files_used": files_used,
        "meta": meta,
    }
