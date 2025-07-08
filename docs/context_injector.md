# `context_injector.py`

**Directory**: `services`
**Purpose**: # Purpose: Manages the aggregation and injection of contextual data from various services into the application's processing flow.

## Upstream
- ENV: —
- Imports: os, pathlib, typing, services.semantic_retriever, services.kb, services.graph, services.summarize_memory

## Downstream
- agents.mcp_agent
- services.context_engine

## Contents
- `build_context()`
- `build_recent_memory_summaries()`
- `load_context()`
- `load_global_context()`
- `load_summary()`
- `safe_truncate()`