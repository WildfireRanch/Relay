# File: agents/trainer_agent.py
# Purpose: Observational learner that improves system logic over time based on plan outcomes, critic responses, and user feedback
# Role: Reflective observer (not judge); future-proofed for RLHF or routing refinements

import logging
from typing import List, Dict, Optional, Any
from datetime import datetime

# Optional: Save insights to long-term memory or database
from services.memory import save_memory_entry


class TrainerAgent:
    def __init__(self):
        self.name = "TrainerAgent"
        self.version = "0.1"
        self.logs = []

    async def run(self, query: str, context: str = "", user_id: str = "system") -> dict:
        """
        Entry point for ad-hoc invocation or reflective prompts.
        Can be used to ask the TrainerAgent for trends, summaries, or insights.
        """
        return {
            "message": "TrainerAgent is a passive learner. Use ingest_results() to provide plan/critic/user data.",
            "status": "ok"
        }

    async def ingest_results(
        self,
        plan: Dict[str, Any],
        critics: List[Dict[str, Any]],
        feedback: Optional[Dict[str, Any]] = None,
        user_id: str = "system"
    ) -> None:
        """
        Main method to observe completed activity:
        - plan: the generated plan dictionary
        - critics: list of critic results with 'passes' and explanation fields
        - feedback: optional user feedback with thumbs up/down, corrections, etc.
        """
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "plan_label": plan.get("label"),
            "critic_summary": [c["name"] + ("✅" if c["passes"] else "❌") for c in critics],
            "feedback": feedback or {},
        }

        # Optional conflict detection
        conflicts = self.detect_conflicts(critics)
        if conflicts:
            log_entry["conflicts"] = conflicts

        # Save to internal buffer or memory system
        self.logs.append(log_entry)
        await save_memory_entry(user_id, {
            "type": "trainer_log",
            "agent": self.name,
            "content": log_entry
        })

    def detect_conflicts(self, critics: List[Dict[str, Any]]) -> List[str]:
        """
        Looks for contradiction among critics — e.g., one fails for logic, another passes for feasibility
        """
        fail_names = {c["name"] for c in critics if not c["passes"]}
        pass_names = {c["name"] for c in critics if c["passes"]}

        # Example: detect if logic failed but impact passed
        if "LogicCritic" in fail_names and "ImpactCritic" in pass_names:
            return ["Logic vs Impact disagreement"]
        
        return []

# Instantiate a shared instance
trainer_agent = TrainerAgent()
