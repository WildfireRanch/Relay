# File: agents/mcp_agent.py
# Directory: agents
# Purpose: Orchestrate MCP: plan -> build context (KB) -> dispatch to route,
#          and emit structured grounding + meta.kb stats for /ask gate.
#
# Back-compat: Keeps the exported run_mcp(...) signature and return shape.
#              Adds 'grounding' list to routed_result and meta.kb.{hits,max_score}.
#
# Env (optional):
#   KB_MIN_SCORE_FLOOR   (default "0.0")  # ignore sources scored below this
#   KB_TOPK_LIMIT        (default "10")   # cap number of sources we surface

from __future__ import annotations

import os
import time
import traceback
from typing import Any, Dict, List, Optional
from uuid import uuid4

# Optional: your structured logger, if available
try:
    from core.logging import log_event
except Exception:  # pragma: no cover
    def log_event(event: str, payload: Dict[str, Any]) -> None:  # type: ignore
        pass

# ── Tunables ────────────────────────────────────────────────────────────────
KB_MIN_SCORE_FLOOR: float = float(os.getenv("KB_MIN_SCORE_FLOOR", "0.0"))
KB_TOPK_LIMIT: int = int(os.getenv("KB_TOPK_LIMIT", "10"))

# ── Integration hooks (map these to your actual modules) ────────────────────
# You likely already have these; we keep imports inside try/except so this file
# can drop in safely and you can fix the mappings one-by-one without outages.

# 1) Planner that returns a plan dict (may include route/final_answer, etc.)
def _plan(query: str, files: List[str], topics: List[str], debug: bool, corr_id: str) -> Dict[str, Any]:
    try:
        from agents.planner_agent import plan  # type: ignore
        return plan(query=query, files=files, topics=topics, debug=debug, corr_id=corr_id) or {}
    except Exception:
        return {
            "objective": f"Answer: {query}",
            "steps": [],
            "route": "echo",
            "_diag": {"coercion_used": True},
        }

# 2) Build context & retrieval (return text context + structured matches)
#    If your context engine already returns structured hits, surface them here.
def _build_context(query: str, files: List[str], topics: List[str], debug: bool, corr_id: str) -> Dict[str, Any]:
    """
    Return:
      {
        "context": str,
        "files_used": List[dict],
        "matches": List[{"path": str, "score": float}],
      }
    """
    try:
        # Preferred: use your real context builder with structured results
        from core.context_engine import build_context  # type: ignore
        ctx = build_context(query=query, files=files, topics=topics, debug=debug, corr_id=corr_id) or {}
        # Expected optional keys: context(str), files_used(list), matches(list of {path, score})
        context = str(ctx.get("context") or "")
        files_used = ctx.get("files_used") or []
        matches = ctx.get("matches") or []
        return {"context": context, "files_used": files_used, "matches": matches}
    except Exception:
        # Fallback: try your KB service directly
        context = ""
        files_used: List[Dict[str, Any]] = []
        matches: List[Dict[str, Any]] = []
        try:
            from services import kb  # type: ignore
            # If kb.search exists, use it; normalize to [{path, score}]
            results = kb.search(query=query, k=KB_TOPK_LIMIT)  # type: ignore
            for r in results or []:
                path = r.get("path") or r.get("file") or r.get("id")
                score = float(r.get("score") or 0.0)
                matches.append({"path": str(path or ""), "score": score})
            # Optionally, build a readable context block (kept for UI)
            lines = ["## 🦙 Semantic Retrieval (Top Matches):"]
            for m in matches:
                if not m["path"]:
                    continue
                lines.append(f"• **{m['path']}** (score: {m['score']:.3f})")
            context = "\n".join(lines)
        except Exception:
            # Absolute fallback: no retrieval
            context = ""
            matches = []
        return {"context": context, "files_used": files_used, "matches": matches}

# 3) Router/dispatcher: run the chosen route/agent and return a result dict
def _dispatch(route: str, query: str, context: str, user_id: str, debug: bool, corr_id: str) -> Dict[str, Any]:
    """
    Return a flexible dict; we'll normalize downstream.
      Examples:
        {"response": "...", "route": "echo"}
        or {"answer": "...", "route": "echo"}
        or {"response": {"text": "...", "meta": {...}}, "route": "echo"}
    """
    try:
        # Prefer a central MCP entry if you have one
        from agents.relay_mcp import dispatch  # type: ignore
        return dispatch(route=route, query=query, context=context, user_id=user_id, debug=debug, corr_id=corr_id) or {}
    except Exception:
        # Fallback: try echo agent
        try:
            from agents.echo_agent import invoke  # type: ignore
            text = invoke(query=query, context=context, user_id=user_id, corr_id=corr_id)
            return {"response": text, "route": "echo"}
        except Exception:
            return {"response": "", "route": route or "echo", "meta": {"error": "dispatch_failed"}}


# ── Utilities ───────────────────────────────────────────────────────────────

def _max_score(matches: List[Dict[str, Any]]) -> Optional[float]:
    mx = None
    for m in matches or []:
        s = m.get("score")
        try:
            f = float(s) if s is not None else None
        except Exception:
            f = None
        if f is None:
            continue
        mx = f if mx is None else max(mx, f)
    return mx

def _filter_matches(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for m in matches or []:
        path = (m.get("path") or "").strip()
        try:
            score = float(m.get("score")) if m.get("score") is not None else 0.0
        except Exception:
            score = 0.0
        if not path:
            continue
        if score < KB_MIN_SCORE_FLOOR:
            continue
        out.append({"path": path, "score": score})
    # cap surfaced sources
    return out[:KB_TOPK_LIMIT]


def _shape_routed_result(raw: Any) -> Dict[str, Any]:
    """
    Normalize routed result to a friendly dict:
      - Prefer 'response' (str or {'text': ...}) then 'answer'
      - Always include 'route'
    """
    if isinstance(raw, dict):
        route = raw.get("route") or "echo"
        response = raw.get("response")
        answer = raw.get("answer")
        if isinstance(response, dict):
            text = response.get("text") or answer or ""
            meta = response.get("meta") or {}
            return {"response": {"text": text, "meta": meta}, "route": route}
        if isinstance(response, str):
            return {"response": response, "route": route}
        if isinstance(answer, str):
            return {"response": answer, "route": route}
        return {"response": "", "route": route}
    elif isinstance(raw, str):
        return {"response": raw, "route": "echo"}
    return {"response": "", "route": "echo"}


# ── Public: run_mcp ─────────────────────────────────────────────────────────

async def run_mcp(
    query: str,
    role: Optional[str] = "planner",
    files: Optional[List[str]] = None,
    topics: Optional[List[str]] = None,
    user_id: str = "anonymous",
    debug: bool = False,
    corr_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Main orchestrator.
    Returns dict with keys (some optional):
      plan, routed_result, critics, context, files_used, meta
    Plus: emits structured grounding in routed_result and meta.kb stats.
    """
    corr_id = corr_id or str(uuid4())
    t0 = time.perf_counter()
    plan: Dict[str, Any] = {}
    context: str = ""
    files_used: List[Dict[str, Any]] = []
    matches: List[Dict[str, Any]] = []

    log_event("mcp_start", {"corr_id": corr_id, "role": role, "user": user_id, "debug": debug})

    # 1) Plan
    t_pl0 = time.perf_counter()
    try:
        plan = _plan(query=query, files=files or [], topics=topics or [], debug=debug, corr_id=corr_id) or {}
    except Exception as e:
        log_event("mcp_plan_error", {"corr_id": corr_id, "error": str(e), "trace": traceback.format_exc()})
        plan = {"route": role or "echo", "_diag": {"plan_error": True}}
    t_pl1 = time.perf_counter()

    # Route may be suggested by planner; default to role/echo
    route = plan.get("route") or role or "echo"

    # 2) Build context + collect retrieval matches (structured)
    t_ctx0 = time.perf_counter()
    try:
        ctx = _build_context(query=query, files=files or [], topics=topics or [], debug=debug, corr_id=corr_id)
        context = str(ctx.get("context") or "")
        files_used = ctx.get("files_used") or []
        matches = _filter_matches(ctx.get("matches") or [])
    except Exception as e:
        log_event("mcp_context_error", {"corr_id": corr_id, "error": str(e), "trace": traceback.format_exc()})
        context, files_used, matches = "", [], []
    t_ctx1 = time.perf_counter()

    # 3) Dispatch to the chosen agent/route
    t_ds0 = time.perf_counter()
    try:
        routed_raw = _dispatch(route=route, query=query, context=context, user_id=user_id, debug=debug, corr_id=corr_id)
    except Exception as e:
        log_event("mcp_dispatch_error", {"corr_id": corr_id, "error": str(e), "trace": traceback.format_exc()})
        routed_raw = {"response": "", "route": route, "meta": {"error": "dispatch_failed"}}
    t_ds1 = time.perf_counter()

    routed_result = _shape_routed_result(routed_raw)

    # 4) Attach structured grounding to the routed result
    if matches:
        # Preserve any grounding already provided by downstream, but ensure it's a list
        if isinstance(routed_result, dict):
            existing = routed_result.get("grounding")
            if not isinstance(existing, list) or not existing:
                routed_result["grounding"] = matches

    # 5) Meta (timings, route, kb stats, corr_id)
    meta: Dict[str, Any] = {
        "request_id": corr_id,
        "origin": plan.get("route") or route,
        "route": route,
        "timings_ms": {
            "planner_ms": int((t_pl1 - t_pl0) * 1000),
            "context_ms": int((t_ctx1 - t_ctx0) * 1000),
            "dispatch_ms": int((t_ds1 - t_ds0) * 1000),
        },
        "planner_diag": plan.get("_diag") or {},
        "kb": {
            "hits": len(matches),
            "max_score": _max_score(matches),
        },
    }

    # (Optional) critics suite — leave as-is if you already populate elsewhere
    critics: Optional[List[Dict[str, Any]]] = None
    try:
        # If you have a critic pipeline, call it here and surface its result
        from agents.critics import evaluate_plan  # type: ignore
        critics = evaluate_plan(plan)  # type: ignore
    except Exception:
        critics = None

    log_event(
        "mcp_done",
        {
            "corr_id": corr_id,
            "route": route,
            "kb_hits": meta["kb"]["hits"],
            "kb_max_score": meta["kb"]["max_score"],
        },
    )

    # 6) Final shape (keeps back-compat keys your /ask expects)
    return {
        "plan": plan,
        "routed_result": routed_result,
        "critics": critics,
        "context": context,
        "files_used": files_used,
        "meta": meta,
    }
