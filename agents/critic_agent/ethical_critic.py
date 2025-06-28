# ✅ performance_critic.py
from .base import BaseCritic

class PerformanceCritic(BaseCritic):
    name = "performance"

    def evaluate(self, plan: dict) -> dict:
        issues = []
        steps = plan.get("steps", [])
        if len(steps) > 10:
            issues.append("Plan has more than 10 steps — may be overengineered.")
        for i, step in enumerate(steps):
            if "loop" in step.lower():
                issues.append(f"Step {i+1} may introduce inefficiency: '{step}'")
        return {
            "name": self.name,
            "passes": not issues,
            "issues": issues
        }

