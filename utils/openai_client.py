# File: utils/openai_client.py
# Directory: utils/
# Purpose: Helper to configure AsyncOpenAI with timeout and retry settings.

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
