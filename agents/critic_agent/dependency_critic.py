# File: agents/critic_agent/dependency_critic.py
# Purpose: Ensure that step order respects logical dependencies or prerequisites

from .base import BaseCritic
from typing import Dict, List

class DependencyCritic(BaseCritic):
    name = "dependency"

    def evaluate(self, plan: Dict) -> Dict:
        issues: List[str] = []
        steps = plan.get("steps", [])

        if not isinstance(steps, list) or len(steps) < 2:
            return {"name": self.name, "passes": True, "issues": []}

        joined_steps = " ".join(s.lower() for s in steps if isinstance(s, str))

        for i, step in enumerate(steps):
            if not isinstance(step, str):
                continue

            if "restart" in step.lower() and "configure" in joined_steps and i < joined_steps.index("configure"):
                issues.append(f"Step {i+1} restarts a service before it is configured: '{step}'")

            if "use" in step.lower() and "install" in joined_steps and i < joined_steps.index("install"):
                issues.append(f"Step {i+1} uses a tool before installation: '{step}'")

        return {
            "name": self.name,
            "passes": not issues,
            "issues": issues
        }
