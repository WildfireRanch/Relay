# ──────────────────────────────────────────────────────────────────────────────
# File: agents/mcp_agent.py
# Purpose:
#   MCP coordinator: builds context, gets a plan (planner or explicit role),
#   routes to the chosen specialist agent, runs critics, logs/ingests results,
#   and always returns a structured result (echo fallback on failure).
#
# Changes in this version:
#   - FIX: critics now receive (artifact, context) instead of (artifact, query)
#   - Pass `plan` to routed handlers (optional kwarg; ignored if not used)
#   - Stronger logging/telemetry (plan_id, route, files_used, context_len)
#   - Optional queue_action() if a handler returns {"action": {...}}
#   - Safer context handling across dict/string shapes
#   - Non-breaking output schema preserved
# ──────────────────────────────────────────────────────────────────────────────

import traceback
import uuid
from typing import Optional, List, Dict, Any

from agents.planner_agent import planner_agent
from agents.control_agent import control_agent
from agents.docs_agent import docs_agent
from agents.codex_agent import codex_agent
from agents.echo_agent import run as echo_agent_run
from agents.simulation_agent import run as simulate_runner
from agents.trainer_agent import trainer_agent
from agents.metaplanner_agent import suggest_route, run as meta_runner
from agents.critic_agent.run import run_critics, run as critic_runner
from agents.memory_agent import run as memory_runner
from agents.janitor_agent import run as janitor_agent

from services.context_injector import build_context
from services.queue import queue_action
from core.logging import log_event

# === Agent Dispatch Map ===
ROUTING_TABLE = {
    "codex":     codex_agent.handle,
    "docs":      docs_agent.analyze,
    "control":   control_agent.run,
    "echo":      echo_agent_run,
    "train":     trainer_agent.run,
    "meta":      meta_runner,
    "critic":    critic_runner,
    "memory":    memory_runner,
    "simulate":  simulate_runner,
    "janitor":   janitor_agent,
}

def extract_plan_for_critics(route: str, routed_result: dict) -> dict:
    """
    Choose what artifact to critique based on route output shape.
    Fallback: return the entire routed_result if unknown.
    """
    if not isinstance(routed_result, dict):
        return {"result": routed_result}

    if route == "codex" and "action" in routed_result:
        return routed_result["action"]
    if route == "docs" and "analysis" in routed_result:
        return routed_result["analysis"]
    if route == "planner" and "plan" in routed_result:
        return routed_result["plan"]

    # Unknown shape → warn and critique the whole result
    log_event("mcp_critic_warning", {
        "route": route,
        "routed_result_keys": list(routed_result.keys()),
    })
    return routed_result

# === MCP Main Loop ===
async def run_mcp(
    query: str,
    files: Optional[List[str]] = None,
    topics: Optional[List[str]] = None,
    role: str = "planner",
    user_id: str = "anonymous",
    debug: bool = False,
) -> Dict[str, Any]:
    """
    Main MCP entry point.

    1) Build context
    2) If role == 'planner': generate plan, allow MetaPlanner override, route accordingly
       Else: route directly to the specified agent role
    3) Run critics on the appropriate artifact
    4) Ingest to trainer
    5) Echo fallback on any failure

    Returns a dict with keys:
      plan | routed_result | critics | context | files_used | [error]
    """
    files = files or []
    topics = topics or []
    request_id = str(uuid.uuid4())

    # === STEP 1: Build Context ===
    try:
        context_data = await build_context(query, files, topics, debug=debug)
        if isinstance(context_data, dict):
            context = context_data.get("context", "") or ""
            files_used = context_data.get("files_used", []) or []
        else:
            context = str(context_data) if context_data is not None else ""
            files_used = []

        log_event("mcp_context_loaded", {
            "request_id": request_id,
            "user": user_id,
            "files_used": files_used,
            "context_len": len(context),
        })
    except Exception as e:
        log_event("mcp_context_error", {
            "request_id": request_id,
            "error": str(e),
            "trace": traceback.format_exc(),
        })
        # Fallback: Echo agent with empty context if context building fails
        routed_result = await echo_agent_run(query=query, context="", user_id=user_id)
        return {
            "plan": None,
            "routed_result": routed_result,
            "critics": None,
            "context": "",
            "files_used": [],
            "error": "Failed to build context.",
        }

    # === STEP 2: AGENT ROUTING AND EXECUTION ===
    try:
        # === PLANNER MODE: default path ===
        if role == "planner":
            # 1) Generate plan
            plan = await planner_agent.ask(query=query, context=context)
            plan_id = plan.get("plan_id") or str(uuid.uuid4())

            # 2) MetaPlanner suggestion
            try:
                suggested = await suggest_route(query=query, plan=plan, user_id=user_id)
                route = suggested if suggested and suggested != plan.get("route") else plan.get("route")
                plan["meta_override"] = route if route and route != plan.get("route") else None
            except Exception as meta_exc:
                log_event("mcp_metaplanner_error", {
                    "request_id": request_id,
                    "plan_id": plan_id,
                    "error": str(meta_exc),
                    "trace": traceback.format_exc(),
                })
                route = plan.get("route")

            if not route:
                route = "echo"

            log_event("mcp_dispatch", {
                "request_id": request_id,
                "role": role,
                "planner_route": plan.get("route"),
                "meta_override": plan.get("meta_override"),
                "final_route": route,
                "plan_id": plan_id,
            })

            # 3) Route to handler (pass plan optionally)
            handler = ROUTING_TABLE.get(route)
            try:
                if handler:
                    # Handlers may accept **kwargs; pass plan for richer context
                    routed_result = await handler(query=query, context=context, user_id=user_id, plan=plan)
                else:
                    log_event("mcp_fallback_echo", {
                        "request_id": request_id,
                        "reason": f"No handler for route '{route}'",
                        "plan_id": plan_id,
                    })
                    routed_result = await echo_agent_run(query=query, context=context, user_id=user_id)
            except Exception as agent_exc:
                log_event("mcp_agent_handler_error", {
                    "request_id": request_id,
                    "role": role,
                    "route": route,
                    "error": str(agent_exc),
                    "trace": traceback.format_exc(),
                    "plan_id": plan_id,
                })
                routed_result = await echo_agent_run(query=query, context=context, user_id=user_id)

            # Optional: enqueue control actions if present
            try:
                if isinstance(routed_result, dict) and "action" in routed_result:
                    queue_action(routed_result["action"])
                    log_event("mcp_action_queued", {
                        "request_id": request_id,
                        "route": route,
                        "action_keys": list(routed_result["action"].keys()),
                    })
            except Exception as qerr:
                log_event("mcp_action_queue_error", {
                    "request_id": request_id,
                    "route": route,
                    "error": str(qerr),
                    "trace": traceback.format_exc(),
                })

            # 4) Critics (FIX: pass CONTEXT, not query)
            try:
                artifact = extract_plan_for_critics(route, routed_result)
                critics = await run_critics(artifact, context)
            except Exception as critic_exc:
                log_event("mcp_critics_error", {
                    "request_id": request_id,
                    "route": route,
                    "error": str(critic_exc),
                    "trace": traceback.format_exc(),
                    "plan_id": plan_id,
                })
                critics = None

            # 5) Trainer ingestion (best-effort, non-fatal)
            try:
                await trainer_agent.ingest_results(
                    query=query,
                    plan=plan,
                    routed_result=routed_result,
                    critics=critics,
                    feedback=None,
                    user_id=user_id,
                )
            except Exception as train_exc:
                log_event("mcp_trainer_ingest_error", {
                    "request_id": request_id,
                    "error": str(train_exc),
                    "trace": traceback.format_exc(),
                    "plan_id": plan_id,
                })

            result = {
                "plan": plan,
                "routed_result": routed_result,
                "critics": critics,
                "context": context,
                "files_used": files_used,
            }

        # === EXPLICIT ROLE MODE: direct dispatch ===
        elif role in ROUTING_TABLE:
            handler = ROUTING_TABLE[role]
            log_event("mcp_dispatch", {
                "request_id": request_id,
                "role": role,
                "context_len": len(context),
            })
            try:
                routed_result = await handler(query=query, context=context, user_id=user_id)
            except Exception as agent_exc:
                log_event("mcp_agent_handler_error", {
                    "request_id": request_id,
                    "role": role,
                    "route": role,
                    "error": str(agent_exc),
                    "trace": traceback.format_exc(),
                })
                routed_result = await echo_agent_run(query=query, context=context, user_id=user_id)

            result = {
                "plan": None,
                "routed_result": routed_result,
                "critics": None,
                "context": context,
                "files_used": files_used,
            }

        # === UNKNOWN ROLE → echo fallback ===
        else:
            log_event("mcp_fallback_echo", {
                "request_id": request_id,
                "reason": f"Unknown role '{role}'",
            })
            routed_result = await echo_agent_run(query=query, context=context, user_id=user_id)
            result = {
                "plan": None,
                "routed_result": routed_result,
                "critics": None,
                "context": context,
                "files_used": files_used,
                "error": f"Unknown role: {role}",
            }

        # === FINAL LOG ===
        log_event("mcp_result", {
            "request_id": request_id,
            "user": user_id,
            "role": role,
            "has_plan": bool(result.get("plan")),
            "route": result.get("plan", {}).get("meta_override") or result.get("plan", {}).get("route"),
            "critics_count": None if result.get("critics") is None else len(result["critics"]),
            "context_len": len(context),
        })

        return {"result": result, "context": context, "files_used": files_used} if debug else result

    # === MCP FATAL → echo fallback ===
    except Exception as e:
        log_event("mcp_agent_error", {
            "request_id": request_id,
            "role": role,
            "error": str(e),
            "trace": traceback.format_exc(),
        })
        routed_result = await echo_agent_run(query=query, context=context, user_id=user_id)
        return {
            "plan": None,
            "routed_result": routed_result,
            "critics": None,
            "context": context,
            "files_used": files_used,
            "error": f"Failed to execute {role} agent.",
        }
