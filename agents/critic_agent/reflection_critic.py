# File: reflection_critic.py
# Directory: agents/critic_agent
# Purpose: # Purpose: Provides a class for evaluating model predictions using reflection-based critique methods.
#
# Upstream:
#   - ENV: —
#   - Imports: base, typing
#
# Downstream:
#   - —
#
# Contents:
#   - ReflectionCritic()
#   - evaluate()









from .base import BaseCritic
from typing import Dict, List

class ReflectionCritic(BaseCritic):
    name = "reflection"

    def evaluate(self, plan: Dict) -> Dict:
        issues: List[str] = []
        steps = plan.get("steps", [])

        # Flag overly long plans
        if len(steps) > 8:
            issues.append("Plan may be too complex — consider simplifying or batching steps.")

        # Look for weak verbs like "maybe", "try", "see if"
        for i, step in enumerate(steps):
            if not isinstance(step, str):
                continue
            lowered = step.lower()
            if any(weak in lowered for weak in ["maybe", "try", "see if"]):
                issues.append(f"Step {i+1} contains indecisive language: '{step}'")

        # Suggest improvement if no recommendation is given
        if not plan.get("recommendation"):
            issues.append("Plan has no recommendation — consider suggesting a follow-up or strategy.")

        return {
            "name": self.name,
            "passes": not issues,
            "issues": issues
        }
