# `neo4j_driver.py`

**Directory**: `services`
**Purpose**: # Purpose: Provides an interface for managing Neo4j database sessions and executing read/write operations.

## Upstream
- ENV: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
- Imports: os, neo4j, contextlib, core.logging

## Downstream
- agents.trainer_agent
- services.graph
- test_graph_neoagent

## Contents
- `execute_read()`
- `execute_write()`
- `get_session()`