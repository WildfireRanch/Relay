# File: agents/critic_agent/clarity_critic.py
# Purpose: Detect vague, underspecified, or ambiguous plan steps

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
