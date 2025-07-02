# File: agents/metaplanner_agent.py
# Purpose: MetaPlanner suggests route overrides based on graph memory (Neo4j) or fallback heuristics

from core.logging import log_event
from services.graph import query_similar_routes  # Optional: replace with your Neo4j utility

# === Suggest a route override based on prior performance or fallback ===
async def suggest_route(query: str, plan: dict, user_id: str = "anonymous") -> str:
    """
    Suggests the most effective route for a query based on:
    - Similar past queries stored in the graph
    - Critic results from previous outcomes
    Falls back to hard-coded heuristics if no graph available.
    """
    original_route = plan.get("route", "echo")
    objective = plan.get("objective", "").lower()
    raw = f"{query} {objective}"

    try:
        # === Graph-based similarity lookup (optional future support) ===
        similar = await query_similar_routes(query)
        if similar:
            # Sort by best past performance (e.g. highest critic pass rate)
            best = max(similar, key=lambda r: r.get("confidence", 0))
            if best and best["route"] != original_route:
                log_event("metaplanner_override", {
                    "query": query,
                    "from": original_route,
                    "to": best["route"],
                    "confidence": best["confidence"]
                })
                return best["route"]

    except Exception as e:
        log_event("metaplanner_graph_fail", {"error": str(e)})

    # === Heuristic fallback suggestions ===
    if "doc" in raw or "kb" in raw or "summary" in raw:
        return "docs"
    if "patch" in raw or "edit" in raw or "fix" in raw:
        return "codex"
    if "toggle" in raw or "sensor" in raw or "shutdown" in raw or "reboot" in raw:
        return "control"
    if "simulate" in raw or "test plan" in raw:
        return "simulate"

    # Default to planner route
    return original_route

# === Agent-standard route handler ===
async def run(message: str, context: str, user_id: str = "anonymous") -> dict:
    """
    Standard Relay agent handler for 'meta' route.
    This allows you to run the MetaPlanner as a standalone agent.

    Returns:
        {
            "suggested_route": "docs",
            "used_fallback": true,
            ...
        }
    """
    try:
        plan = {
            "route": "planner",
            "objective": message,
        }
        suggested = await suggest_route(message, plan, user_id=user_id)
        used_fallback = suggested == plan["route"]
        return {
            "suggested_route": suggested,
            "used_fallback": used_fallback
        }
    except Exception as e:
        log_event("metaplanner_run_fail", {"error": str(e)})
        return {"error": str(e)}
