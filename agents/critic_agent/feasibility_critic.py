# File: agents/critic_agent/feasibility_critic.py
# Purpose: Ensure that steps in the plan are executable based on available context or tools

from .base import BaseCritic
from typing import Dict, List

class FeasibilityCritic(BaseCritic):
    name = "feasibility"

    def evaluate(self, plan: Dict) -> Dict:
        issues: List[str] = []
        steps = plan.get("steps", [])

        for i, step in enumerate(steps):
            if not isinstance(step, str):
                continue

            lowered = step.lower()

            # Naive checks for feasibility constraints
            if "launch spaceship" in lowered:
                issues.append(f"Step {i+1} is not feasible in current environment: '{step}'")

            if "access secret database" in lowered:
                issues.append(f"Step {i+1} may require unavailable credentials: '{step}'")

            if "use non-existent api" in lowered:
                issues.append(f"Step {i+1} references an unavailable tool or endpoint.")

        return {
            "name": self.name,
            "passes": not issues,
            "issues": issues
        }
