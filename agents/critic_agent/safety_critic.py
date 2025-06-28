# File: agents/critic_agent/safety_critic.py

"""
SafetyCritic evaluates a plan for dangerous or destructive steps.

It scans for high-risk keywords that could imply:
- Data loss (delete, drop, overwrite)
- System instability (shutdown, kill, reformat)
- Irreversible actions or commands

The goal is to catch plans that could harm the environment if executed naively.

Future upgrades:
- Context-aware LLM safety scan
- Allow/blocklist per execution context
- Risk scoring or severity levels
"""

from .base import BaseCritic
from typing import Dict, List

class SafetyCritic(BaseCritic):
    name = "safety"

    # Keywords known to imply high-risk system actions
    risky_keywords = [
        "delete", "drop", "overwrite", "shutdown",
        "reformat", "destroy", "kill", "purge",
        "uninstall", "nuke", "wipe", "reset"
    ]

    def evaluate(self, plan: Dict) -> Dict:
        issues: List[str] = []
        steps = plan.get("steps", [])

        for idx, step in enumerate(steps):
            if not isinstance(step, str):
                continue
            lowered = step.lower()
            for keyword in self.risky_keywords:
                if keyword in lowered:
                    issues.append(
                        f"Step {idx+1} contains risky keyword '{keyword}': '{step}'"
                    )

        return {
            "name": self.name,
            "passes": not issues,
            "issues": issues
        }
