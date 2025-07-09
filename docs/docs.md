# `docs.py`

**Directory**: `routes`
**Purpose**: # Purpose: Manages documentation-related operations including viewing, syncing, and organizing documents within the system.

## Upstream
- ENV: —
- Imports: __future__, os, shutil, pathlib, typing, fastapi, fastapi.responses, services.google_docs_sync, services, services.context_engine, services.docs_utils

## Downstream
- main

## Contents
- `_safe_resolve()`
- `full_sync()`
- `list_docs()`
- `mark_priority()`
- `promote_doc()`
- `prune_duplicates()`
- `refresh_kb()`
- `require_api_key()`
- `sync_docs()`
- `view_doc()`