# `memory_agent.py`

**Directory**: `agents`
**Purpose**: # Purpose: Manages the storage, retrieval, and summarization of memory entries within the application.

## Upstream
- ENV: —
- Imports: os, json, pathlib, typing, datetime, core.logging

## Downstream
- agents.mcp_agent

## Contents
- `MemoryAgent()`
- `__init__()`
- `_load_entries()`
- `_summarize_entries()`
- `run()`