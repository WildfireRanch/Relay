# File: agents/critic_agent/run.py
# Purpose: Unified runner for all 15 critics in the Relay Pro Stack
# Dependencies: All critic classes must be implemented and importable

from typing import List, Dict

# Import all 15 critics from their respective modules
from .structure_critic import StructureCritic
from .logic_critic import LogicCritic
from .safety_critic import SafetyCritic
from .clarity_critic import ClarityCritic
from .feasibility_critic import FeasibilityCritic
from .impact_critic import ImpactCritic  # Applied post-pass
from .intent_critic import IntentCritic
from .dependency_critic import DependencyCritic
from .redundancy_critic import RedundancyCritic
from .ethical_critic import EthicalCritic
from .performance_critic import PerformanceCritic
from .reflection_critic import ReflectionCritic
from .consensus_critic import ConsensusCritic
from .temporal_critic import TemporalCritic
from .robustness_critic import RobustnessCritic


def run_critics(plan: Dict, query: str = "", prior_plans: List[Dict] = None) -> List[Dict]:
    """
    Master critic runner. Evaluates a given plan using all 15 defined critics.

    Args:
        plan (dict): The structured plan to be validated.
        query (str): The original user input. Required for IntentCritic.
        prior_plans (List[dict]): Optional list of historical plans for RedundancyCritic or ConsensusCritic.

    Returns:
        List[dict]: A list of critic result dictionaries. Each has:
            - name: str (critic name)
            - passes: bool
            - issues: List[dict] or List[str] (optionally enriched with severity)
    """

    if prior_plans is None:
        prior_plans = []

    core_critics = [
        StructureCritic(),
        LogicCritic(),
        SafetyCritic(),
        ClarityCritic(),
        FeasibilityCritic(),
        IntentCritic(query=query),
        DependencyCritic(),
        RedundancyCritic(prior_plans=prior_plans),
        EthicalCritic(),
        PerformanceCritic(),
        ReflectionCritic(),
        ConsensusCritic(prior_plans=prior_plans),
        TemporalCritic(),
        RobustnessCritic()
    ]

    results = []

    # Evaluate plan using each critic
    for critic in core_critics:
        try:
            result = critic.evaluate(plan)
            results.append(result)
        except Exception as e:
            results.append({
                "name": critic.name,
                "passes": False,
                "issues": [f"Critic error: {str(e)}"]
            })

    # Apply severity scoring to all results (post-pass ImpactCritic pass)
    impact_enricher = ImpactCritic()
    results = [impact_enricher.enrich(result) for result in results]

    return results
import json
from core.logging import log_event

# === Relay-compatible runner ===
async def run(query: str, context: str, user_id: str = "system") -> List[Dict]:
    """
    Handles relay requests to 'critic' role.
    Expects context to be a JSON-encoded plan object.
    """
    try:
        plan = json.loads(context)
        results = run_critics(plan, query=query)

        log_event("critic_agent_result", {
            "user": user_id,
            "passes": all(r.get("passes", False) for r in results),
            "critics": results
        })

        return results

    except Exception as e:
        log_event("critic_agent_fail", {"error": str(e)})
        return [{"name": "CriticAgent", "passes": False, "issues": [f"Failed to run: {str(e)}"]}]
