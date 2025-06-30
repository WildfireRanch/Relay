# File: agents/trainer_agent.py
# Purpose: Observational learner that improves system logic over time based on plan outcomes, critic responses, and user feedback
# Role: Reflective observer (not judge); future-proofed for RLHF or routing refinements

import logging
import os
from typing import List, Dict, Optional, Any
from datetime import datetime

from services.memory import save_memory_entry
from memory.graph_store import Neo4jGraphMemoryStore


class TrainerAgent:
    def __init__(self):
        self.name = "TrainerAgent"
        self.version = "0.1"
        self.logs = []

        # Initialize graph memory store from environment
        self.graph = Neo4jGraphMemoryStore(
            uri=os.getenv("NEO4J_URI"),
            user=os.getenv("NEO4J_USER"),
            password=os.getenv("NEO4J_PASSWORD")
        )

    async def run(self, query: str, context: str = "", user_id: str = "system") -> dict:
        """
        Ad hoc usage (e.g. ask Trainer for trends or system feedback).
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
        Main observer method called after a plan is executed and reviewed.
        Logs:
        - Plan structure
        - Critic evaluations
        - Optional user feedback
        - All relationships to Neo4j
        """

        timestamp = datetime.utcnow().isoformat()
        plan_id = plan.get("label") or f"plan-{datetime.utcnow().timestamp()}"

        # Construct trainer log entry
        log_entry = {
            "timestamp": timestamp,
            "plan_label": plan_id,
            "critic_summary": [c["name"] + ("✅" if c["passes"] else "❌") for c in critics],
            "feedback": feedback or {},
        }

        # Detect critic conflicts (e.g., Logic failed, but Feasibility passed)
        conflicts = self.detect_conflicts(critics)
        if conflicts:
            log_entry["conflicts"] = conflicts

        # Append to in-memory logs and long-term store
        self.logs.append(log_entry)
        await save_memory_entry(user_id, {
            "type": "trainer_log",
            "agent": self.name,
            "content": log_entry
        })

        # === Log to Neo4j graph ===
        # Add the Plan node
        self.graph.add_node("Plan", plan_id, {
            "query": plan.get("input", ""),
            "timestamp": timestamp
        })

        # Add TrainerAgent → Plan observation
        self.graph.add_node("Agent", self.name, {"role": "trainer"})
        self.graph.add_edge(self.name, plan_id, "OBSERVED", {"timestamp": timestamp})

        # Add each Critic result
        for critic in critics:
            critic_id = f"{plan_id}:{critic['name']}"
            self.graph.add_node("Critic", critic_id, {
                "name": critic["name"],
                "passes": critic["passes"],
                "reason": critic.get("reason", "")
            })
            self.graph.add_edge(plan_id, critic_id, "EVALUATED_BY", {
                "passes": critic["passes"]
            })

        # Optional: attach feedback as a node
        if feedback:
            feedback_id = f"{plan_id}:feedback:{user_id}"
            self.graph.add_node("Feedback", feedback_id, {
                "user": user_id,
                "thumbs": feedback.get("thumbs"),
                "comment": feedback.get("comment", "")
            })
            self.graph.add_edge(feedback_id, plan_id, "RATES", {})

    def detect_conflicts(self, critics: List[Dict[str, Any]]) -> List[str]:
        """
        Simple heuristic to detect critic disagreement (e.g. Logic fails, but Impact passes)
        """
        fail_names = {c["name"] for c in critics if not c["passes"]}
        pass_names = {c["name"] for c in critics if c["passes"]}

        if "LogicCritic" in fail_names and "ImpactCritic" in pass_names:
            return ["Logic vs Impact disagreement"]
        
        return []

# Shared instance
trainer_agent = TrainerAgent()

