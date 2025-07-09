# `graph_store.py`

**Directory**: `memory`
**Purpose**: # Purpose: Provides an interface and implementations for storing and managing graph data structures, supporting operations like node and edge manipulation, and querying.

## Upstream
- ENV: —
- Imports: neo4j, typing

## Downstream
- test_graph_direct

## Contents
- `GraphMemoryStore()`
- `Neo4jGraphMemoryStore()`
- `__init__()`
- `add_edge()`
- `add_node()`
- `close()`
- `get_all()`
- `get_connected()`
- `query()`