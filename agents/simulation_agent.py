# File: agents/simulation_agent.py
"""
SimulationAgent for Relay

Runs hypothetical plan executions in a sandboxed environment.
Helps catch errors, safety issues, and performance bottlenecks before real actions.
"""

from typing import List, Dict

class SimulationAgent:
    def __init__(self, sandbox=None):
        # 'sandbox' could be a VM, Docker, dry-run mode, etc.
        self.sandbox = sandbox or {}

    def simulate_plan(self, plan: Dict) -> Dict[str, List[str]]:
        """
        Simulates each step in the plan.
        Returns a log of potential issues per step.
        """
        issues = []
        for idx, step in enumerate(plan.get("steps", []), start=1):
            # Placeholder simulation logic
            if "danger" in step.lower():
                issues.append(f"Step {idx}: potential danger in sandbox")
            if len(step.split()) > 20:
                issues.append(f"Step {idx}: unusually long or complex step")
        return {"plan_simulation_passes": not issues, "issues": issues}

if __name__ == "__main__":
    sim = SimulationAgent()
    plan = {"steps": ["Check system status", "Dangerous delete command", "Cleanup logs"]}
    result = sim.simulate_plan(plan)
    print(result)
