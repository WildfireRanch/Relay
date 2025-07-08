# `kb.py`

**Directory**: `services`
**Purpose**: # Purpose: Manages the knowledge base indexing, search functionality, and embedding operations within the system.

## Upstream
- ENV: KB_EMBED_MODEL, OPENAI_EMBED_MODEL
- Imports: os, json, shutil, logging, pathlib, typing, services.config, llama_index.core, llama_index.core.extractors, llama_index.core.ingestion, llama_index.core.node_parser, llama_index.embeddings.openai, hashlib, sys, time, llama_index.core, llama_index.core

## Downstream
- services.agent
- services.context_injector

## Contents
- `_kb_cli()`
- `_vector_dim_current()`
- `_vector_dim_stored()`
- `api_reindex()`
- `api_search()`
- `embed_all()`
- `ensure_vector_dim_initialized()`
- `get_index()`
- `get_recent_summaries()`
- `index_is_valid()`
- `query_index()`
- `search()`
- `should_index_file()`