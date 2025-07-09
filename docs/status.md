# `status.py`

**Directory**: `routes`
**Purpose**: # Purpose: Provide utilities to fetch and format system status, versioning, and operational context details for monitoring and diagnostics.

## Upstream
- ENV: RELAY_PROJECT_ROOT, RELAY_PROJECT_ROOT
- Imports: fastapi, pathlib, os, subprocess, datetime, subprocess

## Downstream
- main

## Contents
- `fmt_time()`
- `get_context_status()`
- `get_env_status()`
- `get_status_paths()`
- `get_summary()`
- `get_version()`
- `list_context_inventory()`