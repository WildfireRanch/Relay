# memory/graph_store.py

from neo4j import GraphDatabase
from typing import Any, Dict, List, Optional

class GraphMemoryStore:
    def add_node(self, label: str, id: str, properties: Dict[str, Any]) -> None:
        raise NotImplementedError

    def add_edge(self, from_id: str, to_id: str, rel_type: str, properties: Dict[str, Any]) -> None:
        raise NotImplementedError

    def get_connected(self, node_id: str, rel_type: Optional[str] = None) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def query(self, cypher: str, parameters: Dict[str, Any] = {}) -> List[Dict[str, Any]]:
        raise NotImplementedError


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
