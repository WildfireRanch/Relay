# `mcp_agent.py`

**Directory**: `agents`
**Purpose**: # Purpose: Coordinates the execution and interaction of various agent modules to manage complex planning and control tasks within the system.

## Upstream
- ENV: —
- Imports: traceback, typing, agents.planner_agent, agents.control_agent, agents.docs_agent, agents.codex_agent, agents.echo_agent, agents.simulation_agent, agents.trainer_agent, agents.metaplanner_agent, agents.critic_agent.run, agents.memory_agent, agents.janitor_agent, services.context_injector, services.queue, core.logging

## Downstream
- core.relay_mcp
- routes.ask
- routes.mcp

## Contents
- `extract_plan_for_critics()`
- `run_mcp()`