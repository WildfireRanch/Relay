# File: openai_client.py
# Directory: utils
# Purpose: Provides functionality to create and configure a client for interacting with OpenAI's API.
#
# Upstream:
#   - ENV: OPENAI_API_KEY, OPENAI_MAX_RETRIES, OPENAI_TIMEOUT
#   - Imports: httpx, openai, os
#
# Downstream:
#   - agents.codex_agent
#   - agents.docs_agent
#   - agents.echo_agent
#   - agents.planner_agent
#   - routes.ask
#   - services.agent
#   - services.summarize_memory
#
# Contents:
#   - create_openai_client()

import os
import httpx
from openai import AsyncOpenAI


def create_openai_client() -> AsyncOpenAI:
    """Return a configured AsyncOpenAI client using env vars."""
    timeout = float(os.getenv("OPENAI_TIMEOUT", "30"))
    retries = int(os.getenv("OPENAI_MAX_RETRIES", "2"))
    transport = httpx.AsyncHTTPTransport(retries=retries)
    http_client = httpx.AsyncClient(timeout=timeout, transport=transport)
    return AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=http_client)
