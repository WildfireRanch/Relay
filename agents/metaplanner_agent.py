# File: metaplanner_agent.py
# Directory: agents
# Purpose: # Purpose: Provides lightweight heuristics to suggest optimal routes for queries.
#
# Upstream:
#   - ENV: —
#   - Imports: core.logging
#
# Downstream:
#   - agents.mcp_agent
#
# Contents:
#   - run()
#   - suggest_route()









from core.logging import log_event

# === Suggest a route override based on prior performance or fallback ===
async def suggest_route(query: str, plan: dict, user_id: str = "anonymous") -> str:
    """
    Suggests the most effective route for a query using lightweight
    keyword heuristics. Historical graph lookups were removed, so all
    decisions come from these fallbacks.
    """
    original_route = plan.get("route", "echo")
    objective = plan.get("objective", "").lower()
    raw = f"{query} {objective}"

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
async def run(query: str, context: str, user_id: str = "anonymous") -> dict:
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
            "objective": query,
        }
        suggested = await suggest_route(query, plan, user_id=user_id)
        used_fallback = suggested == plan["route"]
        return {
            "suggested_route": suggested,
            "used_fallback": used_fallback
        }
    except Exception as e:
        log_event("metaplanner_run_fail", {"error": str(e)})
        return {"error": str(e)}
