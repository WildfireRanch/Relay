# File: agents/mcp_agent.py
# Purpose: Central orchestrator for Relay — planner-based routing, MetaPlanner override, critic validation, and Trainer logging to Neo4j.

import traceback
from typing import Optional

from agents.planner_agent import planner_agent
from agents.control_agent import control_agent
from agents.docs_agent import docs_agent
from agents.codex_agent import codex_agent
from agents.echo_agent import echo_agent
from agents.simulation_agent import run as simulate_runner
from agents.trainer_agent import trainer_agent
from agents.metaplanner_agent import suggest_route, run as meta_runner
from agents.critic_agent.run import run_critics, run as critic_runner
from agents.memory_agent import run as memory_runner
from agents.janitor_agent import janitor_agent

from services.context_injector import build_context
from services.queue import queue_action
from core.logging import log_event

# === Agent Dispatch Map ===
ROUTING_TABLE = {
    "codex":     codex_agent.handle,
    "docs":      docs_agent.analyze,
    "control":   control_agent.run,
    "echo":      echo_agent.run,
    "train":     trainer_agent.run,
    "meta":      meta_runner,
    "critic":    critic_runner,
    "memory":    memory_runner,
    "simulate":  simulate_runner,
    "janitor":   janitor_agent.run,
}


# === MCP Main Loop ===
async def run_mcp(
    query: str,
    files: Optional[list[str]] = None,
    topics: Optional[list[str]] = None,
    role: str = "planner",
    user_id: str = "anonymous",
    debug: bool = False,
):
    """
    Main MCP entry point.

    Builds context → generates plan (or routes directly) → optionally overrides via MetaPlanner →
    runs routed agent → validates result via critics → logs to graph via TrainerAgent.
    """
    files = files or []
    topics = topics or []

    try:
        context_data = await build_context(query, files, topics, debug=debug)
        context = context_data["context"] if isinstance(context_data, dict) else context_data
        files_used = context_data.get("files_used", []) if isinstance(context_data, dict) else []

    except Exception as e:
        log_event("mcp_context_error", {"error": str(e), "trace": traceback.format_exc()})
        return {"error": "Failed to build context."}

    log_event("mcp_context_loaded", {"user": user_id, "files": files_used})

    try:
        # === PLANNER MODE ===
        if role == "planner":
            plan = await planner_agent.ask(query=query, context=context)

            # 🔁 Override route using MetaPlanner if possible
            suggested = await suggest_route(query=query, plan=plan, user_id=user_id)
            route = suggested if suggested and suggested != plan.get("route") else plan.get("route")
            plan["meta_override"] = route if route != plan.get("route") else None

            log_event("mcp_dispatch", {"role": role, "routed_to": route})

            handler = ROUTING_TABLE.get(route)
            if handler:
                routed_result = await handler(message=query, context=context, user_id=user_id)
            else:
                routed_result = {"response": f"No agent found for route: {route}"}

            critics = await run_critics(routed_result, query)

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
            }

        # === EXPLICIT ROLE MODE ===
        elif role in ROUTING_TABLE:
            handler = ROUTING_TABLE[role]
            log_event("mcp_dispatch", {"role": role})
            routed_result = await handler(message=query, context=context, user_id=user_id)
            result = {"result": routed_result}

        # === UNKNOWN ROLE ===
        else:
            result = {"error": f"Unknown role: {role}"}

        log_event("mcp_result", {"user": user_id, "role": role, "result": result})

        if debug:
            return {"result": result, "context": context, "files_used": files_used}
        return result

    except Exception as e:
        log_event("mcp_agent_error", {"role": role, "error": str(e), "trace": traceback.format_exc()})
        return {"error": f"Failed to execute {role} agent."}
