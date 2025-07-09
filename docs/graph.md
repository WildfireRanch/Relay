# `graph.py`

**Directory**: `services`
**Purpose**: # Purpose: Provides functionalities to interact with graph databases for querying and summarizing route data.

## Upstream
- ENV: —
- Imports: services.neo4j_driver, core.logging

## Downstream
- agents.metaplanner_agent
- services.context_injector

## Contents
- `query_similar_routes()`
- `summarize_recent_context()`