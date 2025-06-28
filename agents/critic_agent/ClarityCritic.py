# ✅ clarity_critic.py (keep this)
from .base import BaseCritic

class ClarityCritic(BaseCritic):
    name = "clarity"

    def evaluate(self, plan: dict) -> dict:
        issues = []
        for i, step in enumerate(plan.get("steps", [])):
            if isinstance(step, str) and ("do something" in step.lower() or "adjust" in step.lower()):
                issues.append(f"Step {i+1} is too vague: '{step}'")
        return {
            "name": self.name,
            "passes": not issues,
            "issues": issues
        }
