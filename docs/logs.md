# `logs.py`

**Directory**: `services`
**Purpose**: # Purpose: Manage logging of application activities and exceptions, and provide access to recent log data.

## Upstream
- ENV: —
- Imports: datetime, json, pathlib, requests, traceback

## Downstream
- routes.context
- routes.logs

## Contents
- `get_recent_logs()`
- `log_and_refresh()`
- `log_entry()`
- `log_exception()`