# File: graph_store.py
# Directory: memory
# Purpose: # Purpose: Provides an interface and implementations for storing and managing graph data structures, supporting operations like node and edge manipulation, and querying.
#
# Upstream:
#   - ENV: —
#   - Imports: neo4j, typing
#
# Downstream:
#   - test_graph_direct
#
# Contents:
#   - GraphMemoryStore()
#   - Neo4jGraphMemoryStore()
#   - __init__()
#   - add_edge()
#   - add_node()
#   - close()
#   - get_all()
#   - get_connected()
#   - query()









from neo4j import GraphDatabase
from typing import Any, Dict, List, Optional


# Abstract base class for graph memory backends
class GraphMemoryStore:
    def add_node(self, label: str, id: str, properties: Dict[str, Any]) -> None:
        raise NotImplementedError

    def add_edge(self, from_id: str, to_id: str, rel_type: str, properties: Dict[str, Any]) -> None:
        raise NotImplementedError

    def get_connected(self, node_id: str, rel_type: Optional[str] = None) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def query(self, cypher: str, parameters: Dict[str, Any] = {}) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def get_all(self) -> Dict[str, List[Dict[str, Any]]]:
        raise NotImplementedError


# Concrete Neo4j implementation
class Neo4jGraphMemoryStore(GraphMemoryStore):
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def add_node(self, label: str, id: str, properties: Dict[str, Any]) -> None:
        with self.driver.session() as session:
            session.run(
                f"MERGE (n:{label} {{id: $id}}) SET n += $props",
                id=id,
                props=properties,
            )

    def add_edge(self, from_id: str, to_id: str, rel_type: str, properties: Dict[str, Any]) -> None:
        with self.driver.session() as session:
            session.run(
                f"""
                MATCH (a {{id: $from_id}}), (b {{id: $to_id}})
                MERGE (a)-[r:{rel_type}]->(b)
                SET r += $props
                """,
                from_id=from_id,
                to_id=to_id,
                props=properties,
            )

    def get_connected(self, node_id: str, rel_type: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.driver.session() as session:
            if rel_type:
                query = f"""
                    MATCH (n {{id: $id}})-[r:{rel_type}]->(m)
                    RETURN m, r
                """
            else:
                query = """
                    MATCH (n {id: $id})-[r]->(m)
                    RETURN m, r
                """
            result = session.run(query, id=node_id)
            return [{"node": r["m"], "relationship": r["r"]} for r in result]

    def query(self, cypher: str, parameters: Dict[str, Any] = {}) -> List[Dict[str, Any]]:
        with self.driver.session() as session:
            result = session.run(cypher, **parameters)
            return [record.data() for record in result]

    def get_all(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Returns:
            - All nodes in the graph with label, ID, and properties
            - All edges with from → to IDs, type, and edge properties
        """
        with self.driver.session() as session:
            node_results = session.run("""
                MATCH (n)
                RETURN labels(n) AS labels, n.id AS id, properties(n) AS props
            """)
            edge_results = session.run("""
                MATCH (a)-[r]->(b)
                RETURN a.id AS from_id, type(r) AS type, b.id AS to_id, properties(r) AS props
            """)

            nodes = [dict(record) for record in node_results]
            edges = [dict(record) for record in edge_results]

            return {"nodes": nodes, "edges": edges}
