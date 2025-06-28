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


# File: agents/critic_agent/run.py
from typing import List, Dict
from .structure_critic import StructureCritic
from .logic_critic import LogicCritic
from .safety_critic import SafetyCritic
from .clarity_critic import ClarityCritic
from .feasibility_critic import FeasibilityCritic
from .intent_critic import IntentCritic
from .dependency_critic import DependencyCritic
from .ethical_critic import EthicalCritic
from .performance_critic import PerformanceCritic
from .impact_critic import ImpactCritic


def run_critics(plan: Dict, query: str = "") -> List[Dict]:
    """
    Run all core critics against a structured plan. Adds severity scoring via ImpactCritic.

    Args:
        plan (Dict): The structured plan to evaluate.
        query (str): The original user query (needed for IntentCritic).

    Returns:
        List[Dict]: Enriched critic results with severity info.
    """
    critics = [
        StructureCritic(),
        LogicCritic(),
        SafetyCritic(),
        ClarityCritic(),
        FeasibilityCritic(),
        IntentCritic(query=query),
        DependencyCritic(),
        EthicalCritic(),
        PerformanceCritic(),
    ]

    raw_results = [critic.evaluate(plan) for critic in critics]
    enriched_results = [ImpactCritic().enrich(r) for r in raw_results]

    return enriched_results
