# File: services/graph.py
# Purpose: Graph query helpers for MetaPlanner (e.g. similar query lookup)

from services.neo4j_driver import neo4j_driver  # assumes driver is initialized separately
from core.logging import log_event

# === Fulltext similarity query using Neo4j index ===
async def query_similar_routes(query: str, top_k: int = 5) -> list[dict]:
    """
    Returns top K similar past queries and their associated routes and critic scores.
    Requires a fulltext index on :Query(text) and proper ROUTED_TO links.
    """
    try:
        cypher = """
        CALL db.index.fulltext.queryNodes('queryTextIndex', $q) YIELD node, score
        MATCH (node)-[:PLANNED_WITH]->(plan:Plan)-[:RAN_ON]->(agent:Agent)
        OPTIONAL MATCH (plan)-[:VALIDATED_BY]->(c:Critic)
        WITH plan, agent, score, COUNT(c) AS total, SUM(CASE WHEN c.passes THEN 1 ELSE 0 END) AS passed
        RETURN agent.name AS route,
               score,
               passed * 1.0 / CASE WHEN total = 0 THEN 1 ELSE total END AS confidence
        ORDER BY confidence DESC, score DESC
        LIMIT $top_k
        """

        records = await neo4j_driver.execute_read(
            cypher,
            parameters={"q": query, "top_k": top_k}
        )

        return [
            {
                "route": record["route"],
                "confidence": float(record["confidence"]),
                "score": float(record["score"])
            }
            for record in records
            if record["route"]
        ]

    except Exception as e:
        log_event("graph_query_fail", {"error": str(e)})
        return []
