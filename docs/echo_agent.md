# `echo_agent.py`

**Directory**: `agents`
**Purpose**: # Purpose: Provides functionality to interact with OpenAI's API for streaming responses, mainly used for echoing user inputs back through a conversational interface.

## Upstream
- ENV: ECHO_MODEL
- Imports: os, typing, openai, core.logging, utils.openai_client

## Downstream
- agents.mcp_agent
- routes.ask

## Contents
- `run()`
- `stream()`