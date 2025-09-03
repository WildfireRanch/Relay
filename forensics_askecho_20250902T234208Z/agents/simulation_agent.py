# File: simulation_agent.py
# Directory: agents
# Purpose: # Purpose: Defines a class to manage and execute simulations based on predefined plans.
#
# Upstream:
#   - ENV: —
#   - Imports: core.logging, json, typing
#
# Downstream:
#   - agents.mcp_agent
#
# Contents:
#   - SimulationAgent()
#   - __init__()
#   - run()
#   - simulate_plan()









from typing import List, Dict, Any
from core.logging import log_event
import json

class SimulationAgent:
    def __init__(self, sandbox=None):
        self.sandbox = sandbox or {}

    def simulate_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulates each step in the plan.
        Returns a log of potential issues per step.
        """
        issues = []
        for idx, step in enumerate(plan.get("steps", []), start=1):
            if "danger" in step.lower():
                issues.append(f"Step {idx}: ⚠️ potential danger in sandbox")
            if len(step.split()) > 20:
                issues.append(f"Step {idx}: ⚠️ unusually long or complex step")
        return {
            "plan_simulation_passes": not issues,
            "issues": issues
        }

# === Exported instance ===
simulation_agent = SimulationAgent()

# === Relay-compatible route handler ===
async def run(query: str, context: str, user_id: str = "system") -> Dict[str, Any]:
    """
    Relay handler for 'simulate' route. Parses plan from context and runs a sandbox check.
    """
    try:
        plan = json.loads(context)
        result = simulation_agent.simulate_plan(plan)
        log_event("simulation_agent_result", {
            "user": user_id,
            "query": query,
            "result": result
        })
        return result
    except Exception as e:
        log_event("simulation_agent_fail", {"error": str(e)})
        return {"error": f"Simulation failed: {str(e)}"}
