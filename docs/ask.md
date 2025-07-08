# `ask.py`

**Directory**: `routes`
**Purpose**: # Purpose: Provides API endpoints for handling various types of requests and interactions with OpenAI models and agents.

## Upstream
- ENV: —
- Imports: traceback, fastapi, fastapi.responses, typing, agents.mcp_agent, agents.codex_agent, agents.echo_agent, utils.openai_client, openai

## Downstream
- main

## Contents
- `ask_codex_stream()`
- `ask_echo_stream()`
- `ask_get()`
- `ask_post()`
- `ask_stream()`
- `test_openai()`