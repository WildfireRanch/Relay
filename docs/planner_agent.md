# `planner_agent.py`

**Directory**: `agents`
**Purpose**: # Purpose: Provides a planning agent that integrates with OpenAI services to generate and manage task plans based on user queries.

## Upstream
- ENV: PLANNER_MODEL
- Imports: os, json, traceback, uuid, openai, core.logging, agents.critic_agent, utils.openai_client

## Downstream
- agents.mcp_agent

## Contents
- `PlannerAgent()`
- `ask()`