# `context.py`

**Directory**: `routes`
**Purpose**: # Purpose: Manage and synchronize documentation context between local and cloud storage, ensuring consistency and updating legacy systems.

## Upstream
- ENV: OPENAI_API_KEY
- Imports: fastapi, services.logs, services.google_docs_sync, openai, pathlib, os, traceback

## Downstream
- —

## Contents
- `ensure_stub_file()`
- `legacy_sync_google()`
- `safe_write_markdown()`
- `sync_docs_and_update()`
- `update_context_summary()`