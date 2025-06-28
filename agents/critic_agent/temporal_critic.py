# File: agents/critic_agent/temporal_critic.py
# Purpose: Ensure steps are ordered correctly in time-sensitive workflows

from .base import BaseCritic
from typing import Dict, List

class TemporalCritic(BaseCritic):
    name = "temporal"

    def evaluate(self, plan: Dict) -> Dict:
        issues: List[str] = []
        steps = plan.get("steps", [])

        if not isinstance(steps, list) or len(steps) < 2:
            return {"name": self.name, "passes": True, "issues": []}

        # Naive temporal check examples
        for i, step in enumerate(steps):
            step_l = step.lower() if isinstance(step, str) else ""

            if "after" in step_l and i == 0:
                issues.append(f"Step 1 uses 'after' but there's nothing before it: '{step}'")

            if "wait" in step_l and not any(s for s in steps[:i] if "start" in s.lower()):
                issues.append(f"Step {i+1} includes 'wait' without an initiating action before it: '{step}'")

        return {
            "name": self.name,
            "passes": not issues,
            "issues": issues
        }
