# File: agents/trainer_agent.py
# Purpose: Observational learner that improves system logic over time based on plan outcomes, critic responses, and user feedback
# Role: Reflective observer (not judge); writes outcomes to graph for MetaPlanner use

from typing import List, Dict, Optional, Any
from datetime import datetime
from core.logging import log_event
from services.neo4j_driver import execute_write

class TrainerAgent:
    def __init__(self):
        self.name = "TrainerAgent"
        self.version = "0.2"
        self.logs = []

    async def run(self, query: str, context: str = "", user_id: str = "system") -> dict:
        """
        Entry point for manual introspection or dashboard calls.
        """
        return {
            "message": "TrainerAgent is passive. Use ingest_results() to write learning events.",
            "status": "ok"
        }

    async def ingest_results(
        self,
        query: str,
        plan: Dict[str, Any],
        routed_result: Dict[str, Any],
        critics: List[Dict[str, Any]],
        feedback: Optional[Dict[str, Any]] = None,
        user_id: str = "system"
    ) -> None:
        """
        Main logging + graph write interface. Records full structure:
        (:Query)-[:PLANNED_WITH]->(:Plan)-[:RAN_ON]->(:Agent)-[:GOT]->(:Result)
                                     \_[:VALIDATED_BY]->(:Critic)
        """
        try:
            plan_id = plan.get("plan_id", f"plan_{datetime.utcnow().timestamp()}")
            query_id = f"query_{hash(query)}"
            agent_name = plan.get("meta_override") or plan.get("route") or "unknown"
            result_id = f"result_{datetime.utcnow().timestamp()}"

            # Save event log (in-memory)
            log_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "query": query,
                "plan_id": plan_id,
                "route": agent_name,
                "passed": plan.get("passes", False),
                "critics": [f"{c['name']} ✅" if c["passes"] else f"{c['name']} ❌" for c in critics],
                "feedback": feedback or {},
            }
            self.logs.append(log_entry)
            log_event("trainer_log", log_entry)

            # Cypher write
            cypher = """
            MERGE (q:Query {id: $query_id})
              ON CREATE SET q.text = $query_text

            MERGE (p:Plan {id: $plan_id})
              SET p.route = $route, p.passed = $passed

            MERGE (a:Agent {name: $route})
            MERGE (r:Result {id: $result_id})
              SET r.timestamp = datetime($now), r.critics_passed = $critics_passed

            MERGE (q)-[:PLANNED_WITH]->(p)
            MERGE (p)-[:RAN_ON]->(a)
            MERGE (a)-[:GOT]->(r)

            FOREACH (c IN $critics |
              MERGE (crit:Critic {name: c.name})
              SET crit.passes = c.passes,
                  crit.issues = c.issues
              MERGE (p)-[:VALIDATED_BY]->(crit)
            )
            """

            await execute_write(cypher, {
                "query_id": query_id,
                "query_text": query,
                "plan_id": plan_id,
                "route": agent_name,
                "passed": plan.get("passes", False),
                "result_id": result_id,
                "now": datetime.utcnow().isoformat(),
                "critics_passed": sum(c["passes"] for c in critics),
                "critics": critics
            })

        except Exception as e:
            log_event("trainer_ingest_fail", {"error": str(e)})

# Instantiate shared singleton
trainer_agent = TrainerAgent()
