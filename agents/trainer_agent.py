# File: agents/trainer_agent.py
# Purpose: Observational learner that improves system logic over time based on plan outcomes, critic responses, and user feedback.
# Role: Reflective observer (not judge); writes outcomes to graph for MetaPlanner use and summarizes training patterns via `run()`.

from typing import List, Dict, Optional, Any
from datetime import datetime
from core.logging import log_event
from services.neo4j_driver import execute_write, execute_read

class TrainerAgent:
    def __init__(self):
        self.name = "TrainerAgent"
        self.version = "0.3"
        self.logs = []

    async def run(self, query: str, context: str = "", user_id: str = "system") -> dict:
        """
        Returns aggregate insights about plan routing and critic performance.
        Can be called via `/train` or `role: train` to inspect recent system behavior.
        """
        try:
            cypher = """
            MATCH (p:Plan)-[:RAN_ON]->(a:Agent)
            OPTIONAL MATCH (p)-[:VALIDATED_BY]->(c:Critic)
            RETURN a.name AS route,
                   COUNT(DISTINCT p) AS plan_count,
                   COUNT(c) AS total_critic_checks,
                   SUM(CASE WHEN c.passes THEN 1 ELSE 0 END) AS passed_critics
            ORDER BY plan_count DESC
            LIMIT 10
            """

            results = await execute_read(cypher)
            summary = {}
            total_plans = 0
            total_critics = 0
            total_passed = 0

            for r in results:
                route = r["route"]
                plans = r["plan_count"]
                critic_checks = r["total_critic_checks"]
                passed = r["passed_critics"]
                summary[route] = {
                    "plans": plans,
                    "critic_pass_rate": round(passed / critic_checks, 3) if critic_checks else None
                }
                total_plans += plans
                total_critics += critic_checks
                total_passed += passed

            return {
                "trainer_summary": summary,
                "global_stats": {
                    "total_plans": total_plans,
                    "total_critic_checks": total_critics,
                    "overall_pass_rate": round(total_passed / total_critics, 3) if total_critics else None
                }
            }

        except Exception as e:
            log_event("trainer_summary_fail", {"error": str(e)})
            return {"error": f"Failed to generate summary: {str(e)}"}

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
