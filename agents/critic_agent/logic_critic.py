# File: agents/critic_agent/logic_critic.py

"""
LogicCritic evaluates the logical structure and coherence of a plan.
It ensures that each step:
- Is a valid string
- Is not duplicated
- Does not loop back to previous steps

Future enhancements may include:
- Causal analysis between steps
- LLM-based coherence scoring
- Dependency validation
"""

from .base import BaseCritic
from typing import Dict, List

class LogicCritic(BaseCritic):
    name = "logic"

    def evaluate(self, plan: Dict) -> Dict:
        issues: List[str] = []
        steps = plan.get("steps")

        if not isinstance(steps, list):
            issues.append("'steps' is not a list")
            return {"name": self.name, "passes": False, "issues": issues}

        seen = set()
        for idx, step in enumerate(steps):
            if not isinstance(step, str):
                issues.append(f"Step {idx+1} is not a string")
                continue
            if step in seen:
                issues.append(f"Step {idx+1} is a duplicate: '{step}'")
            seen.add(step)

        # Coherence check: ensure steps progress logically without re-cycling
        if len(steps) > 1 and steps[-1] in steps[:-1]:
            issues.append("Last step is a repetition of a previous step — potential logic loop")

        # Optional: Warn if the first and last step are suspiciously similar
        if len(steps) > 1 and steps[0].lower() == steps[-1].lower():
            issues.append("First and last steps are identical — possible circular workflow")

        return {"name": self.name, "passes": not issues, "issues": issues}
