# File: agents/critic_agent/base.py
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
