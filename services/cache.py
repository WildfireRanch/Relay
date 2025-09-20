"""Redis helpers (lazy aioredis import, safe on import).

Notes:
- Avoid top-level awaits or demo snippets that break module import.
- Return None from get_redis() when aioredis or REDIS_URL is unavailable.
"""

from typing import Optional
import os
import logging
import hashlib
import json

logger = logging.getLogger("relay.cache")

_aioredis = None


def _get_aioredis():
    """Return aioredis module or None; memoized and import-safe."""
    global _aioredis
    if _aioredis is None:
        try:
            import aioredis  # type: ignore
            _aioredis = aioredis
        except Exception as e:  # pragma: no cover
            logger.info("aioredis unavailable: %s", e)
            _aioredis = False
    return _aioredis or None


_redis = None


async def get_redis():
    """Get a cached aioredis client or None if not available/configured."""
    global _redis
    mod = _get_aioredis()
    url = os.getenv("REDIS_URL")
    if not mod or not url:
        return None
    try:
        if _redis is None:
            _redis = await mod.from_url(url, decode_responses=True)
        return _redis
    except Exception as e:  # pragma: no cover
        logger.info("redis connect failed: %s", e)
        return None


def key_for(*parts: str) -> str:
    """Build a namespaced key from parts (whitespace collapsed)."""
    return ":".join(p.strip().replace(" ", "_") for p in parts if p)


def keyed_hash(namespace: str, payload: dict) -> str:
    """Stable hashed key for arbitrary payload under a namespace."""
    h = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return f"relay:{namespace}:{h}"
