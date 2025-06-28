# File: agents/critic_agent/ethical_critic.py
# Purpose: Flag potentially unethical or non-compliant behavior in plan steps

from .base import BaseCritic
from typing import Dict, List

class EthicalCritic(BaseCritic):
    name = "ethical"

    def evaluate(self, plan: Dict) -> Dict:
        issues: List[str] = []
        steps = plan.get("steps", [])

        for i, step in enumerate(steps):
            if not isinstance(step, str):
                continue

            lowered = step.lower()

            if "scrape user data" in lowered:
                issues.append(f"Step {i+1} may violate privacy policies: '{step}'")

            if "delete logs" in lowered:
                issues.append(f"Step {i+1} could obscure audit trails or accountability: '{step}'")

            if "impersonate" in lowered:
                issues.append(f"Step {i+1} implies deceptive or unauthorized actions: '{step}'")

        return {
            "name": self.name,
            "passes": not issues,
            "issues": issues
        }
