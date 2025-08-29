# File: openai_client.py
# Directory: utils
# Purpose: Provides functionality to create and configure a client for interacting with OpenAI's API.
#
# Upstream:
#   - ENV (required): OPENAI_API_KEY
#   - ENV (optional, granular timeouts):
#       OPENAI_CONNECT_TIMEOUT   (seconds, default 10)
#       OPENAI_READ_TIMEOUT      (seconds, default 45)
#       OPENAI_WRITE_TIMEOUT     (seconds, default 45)
#       OPENAI_POOL_TIMEOUT      (seconds, default 45)
#     Fallback (legacy, single value for all four if set):
#       OPENAI_TIMEOUT           (seconds, default 30)
#   - ENV (optional, connection limits):
#       OPENAI_MAX_KEEPALIVE     (default 20)
#       OPENAI_MAX_CONNECTIONS   (default 100)
#       OPENAI_KEEPALIVE_EXPIRY  (seconds, default 30)
#   - ENV (optional, logical retries at call sites):
#       OPENAI_MAX_RETRIES       (default 2)  # NOTE: Not applied at transport level; callers should implement retries.
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
#
# Notes:
#   - httpx does NOT support `AsyncHTTPTransport(retries=...)`. Using that silently does nothing.
#     We configure proper timeouts and connection limits here and expect callers to implement
#     their own logical retry/backoff (e.g., planner/echo agents).
#   - Keep a single AsyncClient for connection reuse/keep-alive. The OpenAI SDK will use it.

import os
import httpx
from openai import AsyncOpenAI


def _get_float(name: str, default: float) -> float:
    """Fetch a float env var with a safe fallback."""
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _get_int(name: str, default: int) -> int:
    """Fetch an int env var with a safe fallback."""
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def create_openai_client() -> AsyncOpenAI:
    """
    Return a configured AsyncOpenAI client using httpx.AsyncClient with sane timeouts and limits.

    Timeout precedence:
      1) If OPENAI_TIMEOUT is set, it is used for connect/read/write/pool (legacy single knob).
      2) Otherwise, use granular OPENAI_CONNECT_TIMEOUT / READ / WRITE / POOL values.

    Retries:
      - We DO NOT configure transport-level retries (unsupported).
      - Callers (e.g., planner_agent, echo_agent) should implement logical retries/backoff
        using their own loops and asyncio.sleep().
    """
    # ---- timeouts (with legacy single-knob fallback) ------------------------------------------
    legacy_timeout = os.getenv("OPENAI_TIMEOUT")
    if legacy_timeout is not None:
        t = _get_float("OPENAI_TIMEOUT", 30.0)
        timeout = httpx.Timeout(connect=t, read=t, write=t, pool=t)
    else:
        connect = _get_float("OPENAI_CONNECT_TIMEOUT", 10.0)
        read = _get_float("OPENAI_READ_TIMEOUT", 45.0)
        write = _get_float("OPENAI_WRITE_TIMEOUT", 45.0)
        pool = _get_float("OPENAI_POOL_TIMEOUT", 45.0)
        timeout = httpx.Timeout(connect=connect, read=read, write=write, pool=pool)

    # ---- connection limits / keepalive --------------------------------------------------------
    limits = httpx.Limits(
        max_keepalive_connections=_get_int("OPENAI_MAX_KEEPALIVE", 20),
        max_connections=_get_int("OPENAI_MAX_CONNECTIONS", 100),
        keepalive_expiry=_get_float("OPENAI_KEEPALIVE_EXPIRY", 30.0),
    )

    # ---- shared async HTTP client -------------------------------------------------------------
    # NOTE: Do not pass a retries parameter to transports; httpx ignores it for AsyncHTTPTransport.
    http_client = httpx.AsyncClient(timeout=timeout, limits=limits)

    # ---- OpenAI async client ------------------------------------------------------------------
    # The SDK will reuse the httpx client for all requests, benefiting from keep-alive pooling.
    return AsyncOpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        http_client=http_client,
    )
