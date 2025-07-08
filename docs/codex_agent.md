# `codex_agent.py`

**Directory**: `agents`
**Purpose**: # Purpose: Manages interactions with the OpenAI Codex model, handling prompt creation, response parsing, and streaming data for code generation tasks.

## Upstream
- ENV: —
- Imports: os, typing, openai, utils.openai_client, utils.patch_utils, core.logging, dotenv, agents.critic_agent, json, re

## Downstream
- agents.mcp_agent
- routes.ask

## Contents
- `CodexAgent()`
- `_build_prompt()`
- `_parse_codex_response()`
- `handle()`
- `stream()`