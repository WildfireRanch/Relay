# File: robustness_critic.py
# Directory: agents/critic_agent
# Purpose: # Purpose: Provides functionality to assess and critique the robustness of models within the system.
#
# Upstream:
#   - ENV: —
#   - Imports: base, typing
#
# Downstream:
#   - —
#
# Contents:
#   - RobustnessCritic()
#   - evaluate()









from .base import BaseCritic
from typing import Dict, List

class RobustnessCritic(BaseCritic):
    name = "robustness"

    def evaluate(self, plan: Dict) -> Dict:
        issues: List[str] = []
        steps = plan.get("steps", [])

        if not isinstance(steps, list):
            return {"name": self.name, "passes": False, "issues": ["Missing or invalid 'steps' list"]}

        has_fallback = any("fallback" in step.lower() or "if fails" in step.lower() for step in steps if isinstance(step, str))
        has_retry = any("retry" in step.lower() for step in steps if isinstance(step, str))

        if not has_fallback:
            issues.append("No fallback mechanism detected in plan.")

        if not has_retry:
            issues.append("No retry logic found — plan may be brittle to failure.")

        return {
            "name": self.name,
            "passes": not issues,
            "issues": issues
        }
