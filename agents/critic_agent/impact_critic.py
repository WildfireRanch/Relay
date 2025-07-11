# File: impact_critic.py
# Directory: agents/critic_agent
# Purpose: # Purpose: Provides functionality to assess and score the impact of different actions within the system.
#
# Upstream:
#   - ENV: —
#   - Imports: base, typing
#
# Downstream:
#   - —
#
# Contents:
#   - ImpactCritic()
#   - enrich()
#   - score()









from .base import BaseCritic
from typing import Dict, List

class ImpactCritic:
    def enrich(self, critic_result: Dict) -> Dict:
        """
        Add severity level to each issue in a critic's result.
        """
        enriched_issues = []

        for issue in critic_result.get("issues", []):
            if isinstance(issue, str):
                enriched_issues.append({
                    "message": issue,
                    "severity": self.score(issue)
                })
            elif isinstance(issue, dict):
                # Assume already enriched
                enriched_issues.append(issue)

        return {
            "name": critic_result.get("name", "unknown"),
            "passes": critic_result.get("passes", True),
            "issues": enriched_issues
        }

    def score(self, issue: str) -> str:
        """
        Assign severity level based on keywords or phrasing.
        """
        issue = issue.lower()
        if any(k in issue for k in ["delete", "reformat", "overwrite", "destructive"]):
            return "high"
        if any(k in issue for k in ["loop", "duplicate", "vague", "ambiguous"]):
            return "medium"
        return "low"
