# `admin.py`

**Directory**: `routes`
**Purpose**: # Purpose: Provides administrative functionalities like logging, indexing, and system health checks for the web service.

## Upstream
- ENV: —
- Imports: os, shutil, psutil, platform, zipfile, fastapi, fastapi.responses, pathlib, datetime, services.config, services.indexer

## Downstream
- main

## Contents
- `backup_index()`
- `clean_index()`
- `download_log()`
- `health_check()`
- `log_admin_event()`
- `require_api_key()`
- `trigger_reindex()`