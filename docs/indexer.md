# `indexer.py`

**Directory**: `services`
**Purpose**: # Purpose: Provides functionality for indexing directories and files, extracting language data, and managing indexing conditions within the system.

## Upstream
- ENV: KB_EMBED_MODEL, OPENAI_EMBED_MODEL, WIPE_INDEX
- Imports: os, glob, sys, pathlib, llama_index.core, llama_index.embeddings.openai, llama_index.core.node_parser, services.config, shutil

## Downstream
- routes.admin
- routes.index

## Contents
- `collect_code_context()`
- `get_language_from_path()`
- `index_directories()`
- `should_index_file()`