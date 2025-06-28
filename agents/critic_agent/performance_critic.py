# File: agents/critic_agent/performance_critic.py
from .base import BaseCritic

class PerformanceCritic(BaseCritic):
    name = "performance"

    def evaluate(self, plan: dict) -> dict:
        issues = []
        steps = plan.get("steps", [])

        # Check if the plan is overly long
        if len(steps) > 10:
            issues.append("Plan contains more than 10 steps — consider simplifying.")

        # Detect redundant or inefficient step phrasing
        for i, step in enumerate(steps):
            if "loop" in step.lower() or "scan all" in step.lower():
                issues.append(f"Step {i+1} may be inefficient: '{step}'")

            if "repeat" in step.lower():
                issues.append(f"Step {i+1} contains a potential repeat operation.")

        return {
            "name": self.name,
            "passes": not issues,
            "issues": issues
        }
