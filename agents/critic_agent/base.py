# agents/critic_agent/base.py

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


# agents/critic_agent/logic_critic.py

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

        # Basic coherence check: steps should logically build toward the objective
        if len(steps) > 1 and steps[-1] in steps[:-1]:
            issues.append("Last step is a repetition of a previous step — potential loop")

        return {"name": self.name, "passes": not issues, "issues": issues}


# agents/critic_agent/safety_critic.py

from .base import BaseCritic
from typing import Dict, List

class SafetyCritic(BaseCritic):
    name = "safety"
    risky_keywords = ["delete", "drop", "overwrite", "shutdown", "reformat", "destroy", "kill"]

    def evaluate(self, plan: Dict) -> Dict:
        issues: List[str] = []
        steps = plan.get("steps", [])

        for idx, step in enumerate(steps):
            if not isinstance(step, str):
                continue
            for keyword in self.risky_keywords:
                if keyword in step.lower():
                    issues.append(f"Step {idx+1} contains risky keyword '{keyword}': '{step}'")

        return {"name": self.name, "passes": not issues, "issues": issues}


# agents/critic_agent/structure_critic.py

from .base import BaseCritic
from typing import Dict, List

class StructureCritic(BaseCritic):
    name = "structure"

    def evaluate(self, plan: Dict) -> Dict:
        issues: List[str] = []

        if not isinstance(plan.get("objective"), str):
            issues.append("Missing or invalid 'objective' (must be a string)")

        steps = plan.get("steps")
        if not isinstance(steps, list):
            issues.append("Missing or invalid 'steps' (must be a list)")

        if "recommendation" in plan and not isinstance(plan["recommendation"], str):
            issues.append("'recommendation' is present but not a string")

        return {"name": self.name, "passes": not issues, "issues": issues}


# agents/critic_agent/run.py

from .structure_critic import StructureCritic
from .logic_critic import LogicCritic
from .safety_critic import SafetyCritic
from typing import Dict, List

def run_critics(plan: Dict) -> List[Dict]:
    critics = [StructureCritic(), LogicCritic(), SafetyCritic()]
    results = []
    for critic in critics:
        result = critic.evaluate(plan)
        results.append(result)
    return results
