# File: clarity_critic.py
# Directory: agents/critic_agent
# Purpose: # Purpose: Provides functionality to assess and score the clarity of text using predefined linguistic metrics.
#
# Upstream:
#   - ENV: —
#   - Imports: base, typing
#
# Downstream:
#   - —
#
# Contents:
#   - ClarityCritic()
#   - evaluate()







from .base import BaseCritic
from typing import Dict, List

class ClarityCritic(BaseCritic):
    name = "clarity"

    vague_keywords = ["something", "stuff", "things", "etc", "maybe", "try", "improve", "adjust"]

    def evaluate(self, plan: Dict) -> Dict:
        issues: List[str] = []
        steps = plan.get("steps", [])

        for i, step in enumerate(steps):
            if not isinstance(step, str):
                continue
            lowered = step.lower()
            if any(keyword in lowered for keyword in self.vague_keywords):
                issues.append(f"Step {i+1} is vague or underspecified: '{step}'")

        return {
            "name": self.name,
            "passes": not issues,
            "issues": issues
        }
