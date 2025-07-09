# `openai_client.py`

**Directory**: `utils`
**Purpose**: # Purpose: Provides functionality to create and configure a client for interacting with OpenAI's API.

## Upstream
- ENV: OPENAI_TIMEOUT, OPENAI_MAX_RETRIES, OPENAI_API_KEY
- Imports: os, httpx, openai

## Downstream
- agents.codex_agent
- agents.docs_agent
- agents.echo_agent
- agents.planner_agent
- routes.ask
- services.agent
- services.summarize_memory

## Contents
- `create_openai_client()`