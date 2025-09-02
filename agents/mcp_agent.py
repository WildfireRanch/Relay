# File: mcp_agent.py
# Directory: agents
# Purpose: Orchestrates the MCP pipeline for /ask:
#          1) Build context
#          2) Plan (JSON-mode) and meta-route suggestion
#          3) Dispatch to route handler (codex/docs/control/echo/etc.)
#          4) Run critics (non-fatal) and optionally queue actions
#          5) Return routed result with rich meta (origin, route, timings)
#
# Upstream:
#   - ENV (optional): none specific (agents it calls may use their own env)
#   - Imports:
#       - agents.planner_agent.planner_agent
#       - agents.echo_agent.run
#       - agents.codex_agent.handle (if present)
#       - agents.docs_agent.analyze (if present)
#       - agents.control_agent.run (if present)
#       - agents.metaplanner_agent.suggest_route (optional)
#       - agents.critic_agent.run.run_critics (optional; signature: run_critics(plan: Dict, query: str = "", prior_plans: List[Dict] = None))
#       - agents.memory_agent.run (optional)
#       - agents.janitor_agent (optional)
#       - services.context_injector.build_context
#       - services.queue.queue_action (optional)
#       - core.logging.log_event
#
# Downstream:
#   - routes.ask (expects dict with keys: plan, routed_result, critics, context, files_used, [meta])
#
# Public API:
#   - run_mcp(query, role="planner", files=None, topics=None, user_id="anonymous", debug=False)
#
# Notes:
#   - Hardened to avoid “parrot” leakage by surfacing Echo meta (origin/antiparrot) and Planner diag bits.
#   - Critics invocation fixed to pass correct parameters and remain non-fatal.
#   - Adds timings for each stage and bubbles to `meta.timings_ms`.
#   - Always returns a dict (never raises) with best-effort details.

from __future__ import annotations

import asyncio
import traceback
import uuid
from time import monotonic
from typing import Any, Dict, List, Optional, Callable

from core.logging import log_event
from services.context_injector import build_context

# --- Optional agent imports (soft dependencies) ----------------------------------------------
try:
    from agents.planner_agent import planner_agent
except Exception:  # pragma: no cover
    planner_agent = None  # type: ignore

try:
    from agents.echo_agent import run as echo_agent_run  # final-answer / fallback
except Exception:  # pragma: no cover
    echo_agent_run = None  # type: ignore

try:
    from agents.codex_agent import handle as codex_handle
except Exception:  # pragma: no cover
    codex_handle = None  # type: ignore

try:
    from agents.docs_agent import analyze as docs_analyze
except Exception:  # pragma: no cover
    docs_analyze = None  # type: ignore

try:
    from agents.control_agent import run as control_run
except Exception:  # pragma: no cover
    control_run = None  # type: ignore

try:
    from agents.memory_agent import run as memory_run
except Exception:  # pragma: no cover
    memory_run = None  # type: ignore

try:
    from agents.simulation_agent import run as simulate_run
except Exception:  # pragma: no cover
    simulate_run = None  # type: ignore

try:
    from agents.janitor_agent import run as janitor_run
except Exception:  # pragma: no cover
    janitor_run = None  # type: ignore

try:
    from agents.metaplanner_agent import suggest_route
except Exception:  # pragma: no cover
    suggest_route = None  # type: ignore

try:
    from agents.critic_agent.run import run_critics
except Exception:  # pragma: no cover
    run_critics = None  # type: ignore

try:
    from services.queue import queue_action
except Exception:  # pragma: no cover
    queue_action = None  # type: ignore

# --- Routing table ---------------------------------------------------------------------------
ROUTING_TABLE: Dict[str, Optional[Callable[..., Any]]] = {
    "codex": codex_handle,
    "docs": docs_analyze,
    "control": control_run,
    "memory": memory_run,
    "simulate": simulate_run,
    "janitor": janitor_run,
    # "echo" handled explicitly to pass `plan` through
}

# --- Helpers ---------------------------------------------------------------------------------
def _handler_exists(fn: Optional[Callable[..., Any]]) -> bool:
    return callable(fn)

def _extract_artifact_for_critics(route: str, routed_result: Any) -> Dict[str, Any]:
    """
    Map routed_result into an artifact suitable for critics. Best-effort / resilient.
    """
    if not isinstance(routed_result, dict):
        return {"result": str(routed_result)}

    # Heuristics for common agent shapes
    if route == "codex" and "action" in routed_result:
        return routed_result["action"]
    if route == "docs" and "analysis" in routed_result:
        return routed_result["analysis"]
    if "plan" in routed_result and isinstance(routed_result["plan"], dict):
        return routed_result["plan"]

    return routed_result

def _ms(delta_s: float) -> int:
    return int(round(delta_s * 1000))

def _merge_meta(
    base: Dict[str, Any],
    *,
    request_id: str,
    route: str,
    plan_id: Optional[str],
    timings_ms: Dict[str, int],
    upstream_meta: Optional[Dict[str, Any]] = None,
    planner_diag: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Merge upstream meta (e.g., echo meta: origin/antiparrot) with standard fields.
    """
    meta: Dict[str, Any] = {
        "request_id": request_id,
        "route": route,
        "plan_id": plan_id,
        "timings_ms": timings_ms,
    }
    if planner_diag:
        meta.setdefault("planner_diag", planner_diag)

    if upstream_meta and isinstance(upstream_meta, dict):
        # Do not overwrite standard keys unless upstream provides more specific values
        for k, v in upstream_meta.items():
            if v is None:
                continue
            # prefer upstream origin/antiparrot if present
            if k in ("origin", "antiparrot", "sources"):
                meta[k] = v
            elif k not in meta:
                meta[k] = v

    # Append the merged meta into base envelope too, if desired
    base["meta"] = meta
    return meta

async def _call_handler(handler: Callable[..., Any], **kwargs) -> Any:
    """
    Call an async handler or sync fallback in a safe way.
    """
    res = handler(**kwargs)
    if asyncio.iscoroutine(res):
        return await res
    return res

# --- Public API ------------------------------------------------------------------------------

async def run_mcp(
    query: str,
    role: str = "planner",
    files: Optional[List[str]] = None,
    topics: Optional[List[str]] = None,
    user_id: str = "anonymous",
    debug: bool = False,
) -> Dict[str, Any]:
    """
    Execute the MCP flow for a user query.

    Returns:
      {
        "plan": dict|None,
        "routed_result": dict|Any,
        "critics": list|None,
        "context": str,
        "files_used": list,
        "meta": dict,              # <- added (route, plan_id, origin, antiparrot, timings_ms, planner_diag, etc.)
        "error": str|None
      }
    """
    request_id = str(uuid.uuid4())
    files = files or []
    topics = topics or []
    timings: Dict[str, int] = {}

    log_event(
        "mcp_start",
        {"request_id": request_id, "role": role, "files": len(files), "topics": len(topics), "debug": debug},
    )

    # 1) Build context (robust; fall back to echo on failure)
    t0 = monotonic()
    try:
        ctx_res = await build_context(query=query, files=files, topics=topics, debug=debug)
        if isinstance(ctx_res, dict):
            context = ctx_res.get("context", "") or ""
            files_used = ctx_res.get("files_used", []) or []
        else:
            context = str(ctx_res)
            files_used = []
    except Exception as e:
        timings["context_ms"] = _ms(monotonic() - t0)
        log_event(
            "mcp_context_error",
            {"request_id": request_id, "error": str(e), "trace": traceback.format_exc()},
        )
        if _handler_exists(echo_agent_run):
            routed_result = await echo_agent_run(query=query, context="", user_id=user_id)
        else:
            routed_result = {"error": "Context failed and echo unavailable."}
        envelope = {
            "plan": None,
            "routed_result": routed_result,
            "critics": None,
            "context": "",
            "files_used": [],
            "error": "Failed to build context.",
        }
        _merge_meta(
            envelope,
            request_id=request_id,
            route="echo",
            plan_id=None,
            timings_ms=timings,
            upstream_meta=routed_result.get("meta") if isinstance(routed_result, dict) else None,
        )
        return envelope
    timings["context_ms"] = _ms(monotonic() - t0)

    # 2) Routing
    t_plan = monotonic()
    try:
        if role == "planner":
            # 2a) Plan (JSON mode, with retries) — planner is optional but expected
            if planner_agent is None:
                log_event("mcp_missing_planner", {"request_id": request_id})
                plan: Dict[str, Any] = {"route": "echo", "objective": "[no planner available]"}
            else:
                plan = await planner_agent.ask(query=query, context=context)  # type: ignore

            timings["planner_ms"] = _ms(monotonic() - t_plan)
            plan_id = (plan or {}).get("plan_id")
            route = (plan or {}).get("route", "echo")

            # 2b) Meta-planner may override route (non-fatal)
            if suggest_route:
                try:
                    suggested = await suggest_route(query=query, plan=plan, user_id=user_id)  # type: ignore
                    if suggested and suggested != route:
                        log_event(
                            "mcp_meta_override",
                            {"request_id": request_id, "from": route, "to": suggested, "plan_id": plan_id},
                        )
                        route = suggested
                        plan["meta_override"] = route
                except Exception as meta_exc:  # non-fatal
                    log_event(
                        "mcp_metaplanner_error",
                        {"request_id": request_id, "error": str(meta_exc), "plan_id": plan_id},
                    )

            # 2c) Dispatch
            t_dispatch = monotonic()
            if route in ROUTING_TABLE and _handler_exists(ROUTING_TABLE[route]):
                try:
                    handler = ROUTING_TABLE[route]
                    routed_result = await _call_handler(  # type: ignore
                        handler,
                        query=query,
                        context=context,
                        user_id=user_id,
                        plan=plan,
                    )
                except Exception as agent_exc:
                    log_event(
                        "mcp_agent_handler_error",
                        {
                            "request_id": request_id,
                            "route": route,
                            "error": str(agent_exc),
                            "trace": traceback.format_exc(),
                            "plan_id": plan_id,
                        },
                    )
                    if _handler_exists(echo_agent_run):
                        routed_result = await echo_agent_run(query=query, context=context, user_id=user_id, plan=plan)
                        route = "echo"  # fallback route used
                    else:
                        routed_result = {"error": f"Route '{route}' failed and echo unavailable."}
            else:
                # Explicit echo path (or unknown route): pass plan so echo can use `final_answer`
                if _handler_exists(echo_agent_run):
                    routed_result = await echo_agent_run(query=query, context=context, user_id=user_id, plan=plan)
                    route = "echo"
                else:
                    routed_result = {"error": f"Unknown or unsupported route '{route}', echo unavailable."}
            timings["dispatch_ms"] = _ms(monotonic() - t_dispatch)

            # 2d) Critics (best-effort, non-fatal) — FIXED signature
            critics = None
            t_crit = monotonic()
            if run_critics:
                try:
                    artifact = _extract_artifact_for_critics(route, routed_result)
                    # Correct signature: run_critics(plan=..., query=..., prior_plans=optional)
                    critics = await run_critics(plan=artifact, query=query)  # type: ignore
                except Exception as crit_exc:
                    log_event(
                        "mcp_critics_error",
                        {"request_id": request_id, "route": route, "error": str(crit_exc)},
                    )
            timings["critics_ms"] = _ms(monotonic() - t_crit)

            # 2e) Optional queue action (non-fatal)
            if queue_action and isinstance(routed_result, dict) and "action" in routed_result:
                try:
                    queue_action(routed_result["action"])  # type: ignore
                    log_event(
                        "mcp_action_queued",
                        {
                            "request_id": request_id,
                            "route": route,
                            "action_keys": list(routed_result["action"].keys()),
                        },
                    )
                except Exception as qerr:
                    log_event(
                        "mcp_action_queue_error",
                        {"request_id": request_id, "route": route, "error": str(qerr)},
                    )

            # Envelope + meta merge (bubble up Echo/agent meta as well)
            envelope: Dict[str, Any] = {
                "plan": plan,
                "routed_result": routed_result,
                "critics": critics,
                "context": context,
                "files_used": files_used,
            }
            upstream_meta = routed_result.get("meta") if isinstance(routed_result, dict) else None
            planner_diag = None
            if isinstance(plan, dict) and isinstance(plan.get("_diag"), dict):
                planner_diag = plan["_diag"]  # e.g., final_answer_origin, parrot_rejected

            _merge_meta(
                envelope,
                request_id=request_id,
                route=route,
                plan_id=plan_id,
                timings_ms=timings,
                upstream_meta=upstream_meta,
                planner_diag=planner_diag,
            )
            return envelope

        # role != "planner": direct dispatch if available, else echo
        t_role = monotonic()
        if role in ROUTING_TABLE and _handler_exists(ROUTING_TABLE[role]):
            try:
                handler = ROUTING_TABLE[role]
                routed_result = await _call_handler(  # type: ignore
                    handler,
                    query=query,
                    context=context,
                    user_id=user_id,
                )
                route_used = role
            except Exception as agent_exc:
                log_event(
                    "mcp_agent_handler_error",
                    {
                        "request_id": request_id,
                        "role": role,
                        "route": role,
                        "error": str(agent_exc),
                        "trace": traceback.format_exc(),
                    },
                )
                if _handler_exists(echo_agent_run):
                    routed_result = await echo_agent_run(query=query, context=context, user_id=user_id)
                    route_used = "echo"
                else:
                    routed_result = {"error": f"Role '{role}' failed and echo unavailable."}
                    route_used = role
            timings["dispatch_ms"] = _ms(monotonic() - t_role)

            envelope = {
                "plan": None,
                "routed_result": routed_result,
                "critics": None,
                "context": context,
                "files_used": files_used,
            }
            _merge_meta(
                envelope,
                request_id=request_id,
                route=route_used,
                plan_id=None,
                timings_ms=timings,
                upstream_meta=routed_result.get("meta") if isinstance(routed_result, dict) else None,
            )
            return envelope

        # Unknown role → echo
        t_unknown = monotonic()
        if _handler_exists(echo_agent_run):
            routed_result = await echo_agent_run(query=query, context=context, user_id=user_id)
            route_used = "echo"
        else:
            routed_result = {"error": f"Unknown role '{role}', echo unavailable."}
            route_used = role
        timings["dispatch_ms"] = _ms(monotonic() - t_unknown)

        envelope = {
            "plan": None,
            "routed_result": routed_result,
            "critics": None,
            "context": context,
            "files_used": files_used,
            "error": f"Unknown role: {role}",
        }
        _merge_meta(
            envelope,
            request_id=request_id,
            route=route_used,
            plan_id=None,
            timings_ms=timings,
            upstream_meta=routed_result.get("meta") if isinstance(routed_result, dict) else None,
        )
        return envelope

    except Exception as e:
        # Final safety net: log and try echo with available context
        log_event(
            "mcp_exception",
            {"request_id": request_id, "role": role, "error": str(e), "trace": traceback.format_exc()},
        )
        if _handler_exists(echo_agent_run):
            routed_result = await echo_agent_run(query=query, context=context, user_id=user_id)
            route_used = "echo"
        else:
            routed_result = {"error": "MCP failed and echo unavailable."}
            route_used = role

        envelope = {
            "plan": None,
            "routed_result": routed_result,
            "critics": None,
            "context": context,
            "files_used": files_used,
            "error": f"Failed to execute role '{role}'.",
        }
        _merge_meta(
            envelope,
            request_id=request_id,
            route=route_used,
            plan_id=None,
            timings_ms=timings,
            upstream_meta=routed_result.get("meta") if isinstance(routed_result, dict) else None,
        )
        return envelope
