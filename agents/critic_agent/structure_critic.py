# File: structure_critic.py
# Directory: agents/critic_agent
# Purpose: # Purpose: Provides functionality to evaluate and critique the structural aspects of data or models within the application.
#
# Upstream:
#   - ENV: —
#   - Imports: base, typing
#
# Downstream:
#   - —
#
# Contents:
#   - StructureCritic()
#   - evaluate()









"""
StructureCritic validates that a plan conforms to expected schema requirements.

Checks:
- 'objective' exists and is a string
- 'steps' exists and is a list
- if 'recommendation' exists, it must be a string

This is the first line of defense to ensure downstream agents and critics can safely operate.

Future improvements:
- Full pydantic schema validation
- Nested step structure validation
- Enforce minimum step length or count
"""

from .base import BaseCritic
from typing import Dict, List

class StructureCritic(BaseCritic):
    name = "structure"

    def evaluate(self, plan: Dict) -> Dict:
        issues: List[str] = []

        # Required: objective must be a string
        if not isinstance(plan.get("objective"), str):
            issues.append("Missing or invalid 'objective' (must be a string)")

        # Required: steps must be a list
        steps = plan.get("steps")
        if not isinstance(steps, list):
            issues.append("Missing or invalid 'steps' (must be a list of strings)")

        # Optional: recommendation, if present, must be a string
        if "recommendation" in plan and not isinstance(plan["recommendation"], str):
            issues.append("'recommendation' is present but not a string")

        return {
            "name": self.name,
            "passes": not issues,
            "issues": issues
        }
