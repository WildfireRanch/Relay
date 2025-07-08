# ──────────────────────────────────────────────────────────────────────────────
# File: graph.py
# Directory: services
# Purpose: # Purpose: Provides functionalities to interact with graph databases for querying and summarizing route data.
#
# Upstream:
#   - ENV: —
#   - Imports: core.logging, services.neo4j_driver
#
# Downstream:
#   - agents.metaplanner_agent
#   - services.context_injector
#
# Contents:
#   - query_similar_routes()
#   - summarize_recent_context()
# ──────────────────────────────────────────────────────────────────────────────

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
# === Generate text summary of relevant prior routes ===
async def summarize_recent_context(query: str, top_k: int = 5) -> str:
    """
    Returns a markdown-style summary of recent graph memory relevant to the query.
    Used for injecting graph-derived intelligence into planner context.
    """
    try:
        cypher = """
        CALL db.index.fulltext.queryNodes('queryTextIndex', $q) YIELD node, score
        MATCH (node)-[:PLANNED_WITH]->(plan:Plan)-[:RAN_ON]->(agent:Agent)
        OPTIONAL MATCH (plan)-[:VALIDATED_BY]->(c:Critic)
        WITH plan, agent, score,
             COUNT(c) AS total,
             SUM(CASE WHEN c.passes THEN 1 ELSE 0 END) AS passed
        RETURN plan.route AS route,
               agent.name AS agent,
               passed * 1.0 / CASE WHEN total = 0 THEN 1 ELSE total END AS confidence,
               score
        ORDER BY confidence DESC, score DESC
        LIMIT $top_k
        """

        records = await neo4j_driver.execute_read(cypher, {"q": query, "top_k": top_k})
        if not records:
            return ""

        summary = ["### 🔎 Graph Memory Summary"]
        for r in records:
            summary.append(
                f"- `{r['route']}` via `{r['agent']}` → "
                f"Confidence: {r['confidence']:.0%} · Relevance Score: {r['score']:.2f}"
            )

        return "\n".join(summary)

    except Exception as e:
        log_event("graph_summary_fail", {"error": str(e)})
        return ""
