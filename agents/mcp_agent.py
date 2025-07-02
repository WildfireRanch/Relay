# File: agents/mcp_agent.py
# Purpose: Central orchestrator for Relay — planner-based routing, MetaPlanner override,
#          critic validation, and Trainer logging to Neo4j.
#          Echo is primary and fallback agent.

import traceback
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
    "janitor":   janitor_agent
}

def extract_plan_for_critics(route: str, routed_result: dict) -> dict:
    """
    Extract the correct plan/patch/analysis to be critiqued for each agent route.
    Fallback: returns the routed_result and logs a warning if shape is unknown.
    """
    if route == "codex" and "action" in routed_result:
        return routed_result["action"]
    elif route == "docs" and "analysis" in routed_result:
        return routed_result["analysis"]
    elif route == "planner" and "plan" in routed_result:
        return routed_result["plan"]
    # Add more route keys as needed for other agent types
    else:
        log_event("mcp_critic_warning", {
            "route": route,
            "routed_result_keys": list(routed_result.keys())
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

    Builds context → generates plan (or routes directly) → optionally overrides via MetaPlanner →
    runs routed agent → validates result via critics → logs to graph via TrainerAgent.

    Echo is the primary and fallback agent: if no other handler is routed or errors,
    Echo will always handle the request.
    """
    files = files or []
    topics = topics or []

    try:
        context_data = await build_context(query, files, topics, debug=debug)
        context = context_data["context"] if isinstance(context_data, dict) else context_data
        files_used = context_data.get("files_used", []) if isinstance(context_data, dict) else []

    except Exception as e:
        log_event("mcp_context_error", {"error": str(e), "trace": traceback.format_exc()})
        # Echo always as fallback, even if context build fails
        fallback = await echo_agent_run(message=query, context="", user_id=user_id)
        return {
            "plan": None,
            "routed_result": fallback,
            "critics": None,
            "context": "",
            "files_used": [],
            "error": "Failed to build context."
        }

    log_event("mcp_context_loaded", {"user": user_id, "files": files_used})

    try:
        # === PLANNER MODE ===
        if role == "planner":
            plan = await planner_agent.ask(query=query, context=context)

            # 🔁 Override route using MetaPlanner if possible
            suggested = await suggest_route(query=query, plan=plan, user_id=user_id)
            route = suggested if suggested and suggested != plan.get("route") else plan.get("route")
            plan["meta_override"] = route if route != plan.get("route") else None

            log_event("mcp_dispatch", {
                "role": role,
                "planner_route": plan.get("route"),
                "meta_override": plan.get("meta_override")
            })

            handler = ROUTING_TABLE.get(route)
            routed_result = None
            try:
                if handler:
                    routed_result = await handler(message=query, context=context, user_id=user_id)
                else:
                    log_event("mcp_fallback_echo", {"reason": f"No handler for route '{route}'"})
                    routed_result = await echo_agent_run(message=query, context=context, user_id=user_id)
            except Exception as agent_exc:
                log_event("mcp_agent_handler_error", {
                    "role": role,
                    "route": route,
                    "error": str(agent_exc),
                    "trace": traceback.format_exc()
                })
                routed_result = await echo_agent_run(message=query, context=context, user_id=user_id)

            # --- Critic Validation: always pass the extracted plan/patch, and user query (not context!) ---
            plan_to_critique = extract_plan_for_critics(route, routed_result)
            critics = run_critics(plan_to_critique, query)

            await trainer_agent.ingest_results(
                query=query,
                plan=plan,
                routed_result=routed_result,
                critics=critics,
                feedback=None,
                user_id=user_id,
            )

            result = {
                "plan": plan,
                "routed_result": routed_result,
                "critics": critics,
                "context": context,
                "files_used": files_used,
            }

        # === EXPLICIT ROLE MODE ===
        elif role in ROUTING_TABLE:
            handler = ROUTING_TABLE[role]
            log_event("mcp_dispatch", {"role": role})
            try:
                routed_result = await handler(message=query, context=context, user_id=user_id)
            except Exception as agent_exc:
                log_event("mcp_agent_handler_error", {
                    "role": role,
                    "route": role,
                    "error": str(agent_exc),
                    "trace": traceback.format_exc()
                })
                routed_result = await echo_agent_run(message=query, context=context, user_id=user_id)
            result = {
                "plan": None,
                "routed_result": routed_result,
                "critics": None,
                "context": context,
                "files_used": files_used,
            }

        # === UNKNOWN ROLE ===
        else:
            # Unknown role: always fallback to Echo
            log_event("mcp_fallback_echo", {"reason": f"Unknown role '{role}'"})
            routed_result = await echo_agent_run(message=query, context=context, user_id=user_id)
            result = {
                "plan": None,
                "routed_result": routed_result,
                "critics": None,
                "context": context,
                "files_used": files_used,
                "error": f"Unknown role: {role}"
            }

        log_event("mcp_result", {"user": user_id, "role": role, "result": result})

        if debug:
            return {"result": result, "context": context, "files_used": files_used}
        return result

    except Exception as e:
        log_event("mcp_agent_error", {"role": role, "error": str(e), "trace": traceback.format_exc()})
        # Echo as final fallback if MCP main loop itself errors
        routed_result = await echo_agent_run(message=query, context=context, user_id=user_id)
        return {
            "plan": None,
            "routed_result": routed_result,
            "critics": None,
            "context": context,
            "files_used": files_used,
            "error": f"Failed to execute {role} agent."
        }
