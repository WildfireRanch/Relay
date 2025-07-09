# File: base.py
# Directory: agents/critic_agent
# Purpose: # Purpose: Provide abstract base classes for creating critic components in the system, enforcing a standard interface for evaluation methods.
#
# Upstream:
#   - ENV: —
#   - Imports: abc, typing
#
# Downstream:
#   - —
#
# Contents:
#   - BaseCritic()
#   - evaluate()








from abc import ABC, abstractmethod
from typing import Dict, List

class BaseCritic(ABC):
    name: str

    @abstractmethod
    def evaluate(self, plan: Dict) -> Dict:
        """
        Evaluate the given plan.

        Returns:
            {
                "name": self.name,
                "passes": bool,
                "issues": List[str]
            }
        """
        pass
