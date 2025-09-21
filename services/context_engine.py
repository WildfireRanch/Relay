# File: services/context_engine.py
# Purpose: Back-compat shim during Phase 2 → Phase 3.
import logging
import threading
from typing import Any, Callable, Dict, List

from core.context_engine import (  # re-export
    ContextEngine as _CoreContextEngine,
    ContextRequest,
    ContextResult,
    EngineConfig,
    RetrievalTier,
    Retriever,
    build_context,
)

logger = logging.getLogger(__name__)

_CACHE_LOCK = threading.Lock()
_CACHE_VERSION = 0


def _lru_clearables() -> List[Callable[[], None]]:
    """Return cache_clear callables for any functools.lru_cache objects here."""
    clearables: List[Callable[[], None]] = []
    # No local lru_cache wrappers today; placeholder for future additions.
    return clearables


def _real_clear_cache() -> Dict[str, object]:
    """Best-effort cache invalidation; never raises."""

    cleared = 0
    with _CACHE_LOCK:
        global _CACHE_VERSION
        for cache_clear in _lru_clearables():
            try:
                cache_clear()
                cleared += 1
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("context cache clear skipped: %s", exc)
        _CACHE_VERSION += 1
        version = _CACHE_VERSION

    logger.info("context_engine.clear_cache", extra={"cleared": cleared, "version": version})
    return {"ok": True, "cleared": cleared, "version": version}


setattr(_CoreContextEngine, "clear_cache", staticmethod(_real_clear_cache))

# Convenience module-level APIs (back-compat, never raise)
def clear_cache() -> Dict[str, Any]:
    """Clear any local caches used by the context engine. Safe to call.

    Returns a small status dict: { ok, cleared, version? , reason? }.
    """
    try:
        return _real_clear_cache()
    except Exception as e:  # pragma: no cover
        logger.warning("context_engine.clear_cache failed: %s", e)
        return {"ok": False, "cleared": False, "reason": str(e)}


def cache_status() -> Dict[str, Any]:
    """Return a lightweight snapshot of cache state (no side effects)."""
    try:
        with _CACHE_LOCK:
            version = _CACHE_VERSION
        return {
            "ok": True,
            "version": version,
            "caches": {
                "retriever": {"items": 0, "enabled": False},
                "embeddings": {"items": 0, "enabled": False},
            },
            "notes": ["shim; no active caches"],
        }
    except Exception as e:  # pragma: no cover
        return {"ok": False, "caches": {}, "error": str(e)}

# Public alias so importers keep working.
ContextEngine = _CoreContextEngine


__all__ = [
    "build_context",
    "ContextRequest",
    "EngineConfig",
    "RetrievalTier",
    "Retriever",
    "ContextResult",
    "ContextEngine",
    "clear_cache",
    "cache_status",
]

# Note: This module keeps compatibility-only utilities; once service-layer
# caching returns, replace `_noop_clear_cache` with the real implementation.
