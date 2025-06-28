# File: agents/critic_agent/consensus_critic.py
# Purpose: Detect divergence across multiple plans or agent runs

from .base import BaseCritic
from typing import Dict, List

class ConsensusCritic(BaseCritic):
    name = "consensus"

    def __init__(self, prior_plans: List[Dict] = None):
        self.prior_plans = prior_plans or []

    def evaluate(self, plan: Dict) -> Dict:
        issues: List[str] = []

        current_steps = set(step.lower() for step in plan.get("steps", []) if isinstance(step, str))

        for idx, prior in enumerate(self.prior_plans):
            prior_steps = set(step.lower() for step in prior.get("steps", []) if isinstance(step, str))
            disagreement = current_steps.symmetric_difference(prior_steps)

            if len(disagreement) > 2:
                issues.append(f"Plan differs significantly from prior plan #{idx + 1} — {len(disagreement)} divergent steps.")

        return {
            "name": self.name,
            "passes": not issues,
            "issues": issues
        }
