# File: intent_critic.py
# Directory: agents/critic_agent
# Purpose: # Purpose: Provides a class to evaluate the alignment and quality of user intents within the system.
#
# Upstream:
#   - ENV: —
#   - Imports: base, typing
#
# Downstream:
#   - —
#
# Contents:
#   - IntentCritic()
#   - __init__()
#   - evaluate()









from .base import BaseCritic
from typing import Dict, List

class IntentCritic(BaseCritic):
    name = "intent"

    def __init__(self, query: str):
        self.query = query.lower().strip() if query else ""

    def evaluate(self, plan: Dict) -> Dict:
        issues: List[str] = []
        objective = plan.get("objective", "").lower()
        steps = plan.get("steps", [])
        joined_steps = " ".join(steps).lower() if isinstance(steps, list) else ""

        if not self.query:
            issues.append("Original user query is missing.")
        elif self.query not in objective and self.query not in joined_steps:
            issues.append("Plan objective or steps do not reference user query keywords.")

        if len(objective.split()) < 3:
            issues.append("Objective is too short to reflect meaningful alignment.")

        return {
            "name": self.name,
            "passes": not issues,
            "issues": issues
        }
