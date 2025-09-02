# File: mcp_agent.py
# Directory: agents
# Purpose: Orchestrates the MCP pipeline for /ask:
#          1) Build context
#          2) Plan (JSON-mode) and meta-route suggestion
#          3) Dispatch to route handler (codex/docs/control/echo/etc.)
#          4) Run critics (non-fatal) and optionally queue actions
#          5) Return routed result with rich meta (origin, route, timings)

from __future__ import annotations

import asyncio
import traceback
import uuid
from time import monotonic
from typing import Any, Dict, List, Optional, Callable

from core.logging import log_event
from services.context_injector import build_context

# --- Optional agent imports (soft dependencies)
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


ROUTING_TABLE: Dict[str, Optional[Callable[..., Any]]] = {
    "codex": codex_handle,
    "docs": docs_analyze,
    "control": control_run,
    "memory": memory_run,
    "simulate": simulate_run,
    "janitor": janitor_run,
    # "echo" handled explicitly to pass `plan` through
}

def _handler_exists(fn: Optional[Callable[..., Any]]) -> bool:
    return callable(fn)

def _extract_artifact_for_critics(route: str, routed_result: Any) -> Dict[str, Any]:
    if not isinstance(routed_result, dict):
        return {"result": str(routed_result)}
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
    meta: Dict[str, Any] = {
        "request_id": request_id,
        "route": route,
        "plan_id": plan_id,
        "timings_ms": timings_ms,
    }
    if planner_diag:
        meta.setdefault("planner_diag", planner_diag)

    if upstream_meta and isinstance(upstream_meta, dict):
        for k, v in upstream_meta.items():
            if v is None:
                continue
            if k in ("origin", "antiparrot", "sources"):
                meta[k] = v
            elif k not in meta:
                meta[k] = v

    base["meta"] = meta
    return meta

async def _call_handler(handler: Callable[..., Any], **kwargs) -> Any:
    res = handler(**kwargs)
    if asyncio.iscoroutine(res):
        return await res
    return res


async def run_mcp(
    query: str,
    role: str = "planner",
    files: Optional[List[str]] = None,
    topics: Optional[List[str]] = None,
    user_id: str = "anonymous",
    debug: bool = False,
) -> Dict[str, Any]:
    request_id = str(uuid.uuid4())
    files = files or []
    topics = topics or []
    timings: Dict[str, int] = {}

    log_event(
        "mcp_start",
        {"request_id": request_id, "role": role, "files": len(files), "topics": len(topics), "debug": debug},
    )

    # 1) Build context
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
        log_event("mcp_context_error", {"request_id": request_id, "error": str(e), "trace": traceback.format_exc()})
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
            # 2a) Plan
            if planner_agent is None:
                log_event("mcp_missing_planner", {"request_id": request_id})
                plan: Dict[str, Any] = {"route": "echo", "objective": "[no planner available]"}
            else:
                plan = await planner_agent.ask(query=query, context=context)  # type: ignore

            timings["planner_ms"] = _ms(monotonic() - t_plan)
            plan_id = (plan or {}).get("plan_id")
            route = (plan or {}).get("route", "echo")

            # 2b) Meta-planner override (non-fatal)
            if suggest_route:
                try:
                    suggested = await suggest_route(query=query, plan=plan, user_id=user_id)  # type: ignore
                    if suggested and suggested != route:
                        log_event("mcp_meta_override", {"request_id": request_id, "from": route, "to": suggested, "plan_id": plan_id})
                        route = suggested
                        plan["meta_override"] = route
                except Exception as meta_exc:
                    log_event("mcp_metaplanner_error", {"request_id": request_id, "error": str(meta_exc), "plan_id": plan_id})

            # 2c) Dispatch
            t_dispatch = monotonic()
            if route in ROUTING_TABLE and _handler_exists(ROUTING_TABLE[route]):
                try:
                    handler = ROUTING_TABLE[route]
                    routed_result = await _call_handler(  # type: ignore
                        handler, query=query, context=context, user_id=user_id, plan=plan
                    )
                except Exception as agent_exc:
                    log_event(
                        "mcp_agent_handler_error",
                        {"request_id": request_id, "route": route, "error": str(agent_exc), "trace": traceback.format_exc(), "plan_id": plan_id},
                    )
                    if _handler_exists(echo_agent_run):
                        routed_result = await echo_agent_run(query=query, context=context, user_id=user_id, plan=plan)
                        route = "echo"
                    else:
                        routed_result = {"error": f"Route '{route}' failed and echo unavailable."}
            else:
                if _handler_exists(echo_agent_run):
                    routed_result = await echo_agent_run(query=query, context=context, user_id=user_id, plan=plan)
                    route = "echo"
                else:
                    routed_result = {"error": f"Unknown or unsupported route '{route}', echo unavailable."}
            timings["dispatch_ms"] = _ms(monotonic() - t_dispatch)

            # 2d) Critics (best-effort, non-fatal) — sync or async
            critics = None
            t_crit = monotonic()
            if run_critics:
                try:
                    artifact = _extract_artifact_for_critics(route, routed_result)
                    res = run_critics(plan=artifact, query=query)  # may be sync or async
                    if asyncio.iscoroutine(res):
                        critics = await res  # type: ignore
                    else:
                        critics = res  # type: ignore
                except Exception as crit_exc:
                    log_event("mcp_critics_error", {"request_id": request_id, "route": route, "error": str(crit_exc)})
            timings["critics_ms"] = _ms(monotonic() - t_crit)

            # 2e) Optional queue action (non-fatal)
            if queue_action and isinstance(routed_result, dict) and "action" in routed_result:
                try:
                    queue_action(routed_result["action"])  # type: ignore
                    log_event("mcp_action_queued", {"request_id": request_id, "route": route, "action_keys": list(routed_result["action"].keys())})
                except Exception as qerr:
                    log_event("mcp_action_queue_error", {"request_id": request_id, "route": route, "error": str(qerr)})

            # Envelope + meta merge
            envelope: Dict[str, Any] = {
                "plan": plan,
                "routed_result": routed_result,
                "critics": critics,
                "context": context,
                "files_used": files_used,
            }
            upstream_meta = routed_result.get("meta") if isinstance(routed_result, dict) else None
            planner_diag = plan.get("_diag") if isinstance(plan, dict) else None

            _merge_meta(
                envelope,
                request_id=request_id,
                route=route,
                plan_id=plan_id,
                timings_ms=timings,
                upstream_meta=upstream_meta,
                planner_diag=planner_diag if isinstance(planner_diag, dict) else None,
            )
            return envelope

        # role != "planner": direct dispatch if available, else echo
        t_role = monotonic()
        if role in ROUTING_TABLE and _handler_exists(ROUTING_TABLE[role]):
            try:
                handler = ROUTING_TABLE[role]
                routed_result = await _call_handler(  # type: ignore
                    handler, query=query, context=context, user_id=user_id
                )
                route_used = role
            except Exception as agent_exc:
                log_event(
                    "mcp_agent_handler_error",
                    {"request_id": request_id, "role": role, "route": role, "error": str(agent_exc), "trace": traceback.format_exc()},
                )
                if _handler_exists(echo_agent_run):
                    routed_result = await echo_agent_run(query=query, context=context, user_id=user_id)
                    route_used = "echo"
                else:
                    routed_result = {"error": f"Role '{role}' failed and echo unavailable."}
                    route_used = role
        else:
            if _handler_exists(echo_agent_run):
                routed_result = await echo_agent_run(query=query, context=context, user_id=user_id)
                route_used = "echo"
            else:
                routed_result = {"error": f"Unknown role '{role}', echo unavailable."}
                route_used = role
        timings["dispatch_ms"] = _ms(monotonic() - t_role)

        envelope = {
            "plan": None,
            "routed_result": routed_result,
            "critics": None,
            "context": context,
            "files_used": files_used,
            "error": f"Unknown role: {role}" if route_used != role and role not in ROUTING_TABLE else None,
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
        # Final safety net
        log_event("mcp_exception", {"request_id": request_id, "role": role, "error": str(e), "trace": traceback.format_exc()})
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
