# `control_agent.py`

**Directory**: `agents`
**Purpose**: # Purpose: Provides an interface for managing and controlling system services, including starting, restarting, and cache management.

## Upstream
- ENV: —
- Imports: typing, core.logging, subprocess, shlex

## Downstream
- agents.mcp_agent
- routes.control

## Contents
- `ControlAgent()`
- `__init__()`
- `_run_command()`
- `clear_cache()`
- `echo_command()`
- `restart_service()`
- `run()`