# `logging.py`

**Directory**: `core`
**Purpose**: # Purpose: Provide centralized logging functionality for system events and errors.

## Upstream
- ENV: —
- Imports: datetime, json

## Downstream
- agents.codex_agent
- agents.control_agent
- agents.critic_agent.run
- agents.docs_agent
- agents.echo_agent
- agents.mcp_agent
- agents.memory_agent
- agents.metaplanner_agent
- agents.planner_agent
- agents.simulation_agent
- agents.trainer_agent
- routes.codex
- services.graph
- services.neo4j_driver
- utils.logger

## Contents
- `log_event()`