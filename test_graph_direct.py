from memory.graph_store import Neo4jGraphMemoryStore
import os

store = Neo4jGraphMemoryStore(
    uri="neo4j+s://ed6f9d10.databases.neo4j.io",
    user="neo4j",
    password="I5TraIThc7_-aIEmd4gq-4HHKPTO-p0GOTN_5tD-K8g"
)

# Add nodes and edge
store.add_node("Agent", "planner", {"role": "MCP"})
store.add_node("Plan", "plan-001", {"summary": "Test routing to Codex"})
store.add_edge("planner", "plan-001", "GENERATED", {"timestamp": "2025-06-30"})

# Query it back
results = store.get_connected("planner")
print("Connections:", results)

store.close()
