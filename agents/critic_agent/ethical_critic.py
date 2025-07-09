# File: ethical_critic.py
# Directory: agents/critic_agent
# Purpose: # Purpose: Provides a class to evaluate actions or decisions based on ethical guidelines and principles.
#
# Upstream:
#   - ENV: —
#   - Imports: base, typing
#
# Downstream:
#   - —
#
# Contents:
#   - EthicalCritic()
#   - evaluate()









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
