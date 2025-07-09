# File: redundancy_critic.py
# Directory: agents/critic_agent
# Purpose: # Purpose: Provides a class to evaluate and critique redundancy levels in data or processes.
#
# Upstream:
#   - ENV: —
#   - Imports: base, typing
#
# Downstream:
#   - —
#
# Contents:
#   - RedundancyCritic()
#   - __init__()
#   - evaluate()









from .base import BaseCritic
from typing import Dict, List

class RedundancyCritic(BaseCritic):
    name = "redundancy"

    def __init__(self, prior_plans: List[Dict] = None):
        self.prior_plans = prior_plans or []

    def evaluate(self, plan: Dict) -> Dict:
        issues: List[str] = []
        current_steps = [s.lower() for s in plan.get("steps", []) if isinstance(s, str)]

        # Check for internal duplicates
        seen = set()
        for i, step in enumerate(current_steps):
            if step in seen:
                issues.append(f"Step {i+1} is a duplicate within the current plan: '{step}'")
            seen.add(step)

        # Compare against prior plans
        for i, prior in enumerate(self.prior_plans):
            prior_steps = [s.lower() for s in prior.get("steps", []) if isinstance(s, str)]
            overlap = set(current_steps).intersection(prior_steps)
            if overlap:
                issues.append(f"Plan repeats {len(overlap)} step(s) from prior plan #{i+1}: {sorted(overlap)}")

        return {
            "name": self.name,
            "passes": not issues,
            "issues": issues
        }
