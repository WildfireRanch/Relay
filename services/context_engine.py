# File: services/contextengine.py
# Purpose: Back-compat shim during Phase 2 → Phase 3.
from core.context_engine import (  # re-export
    ContextEngine as _CoreContextEngine,
    ContextRequest,
    ContextResult,
    EngineConfig,
    RetrievalTier,
    Retriever,
    build_context,
)


def _noop_clear_cache() -> None:
    """Placeholder; wire real cache invalidation when services layer returns."""
    return


setattr(_CoreContextEngine, "clear_cache", staticmethod(_noop_clear_cache))

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
]

# Note: This module keeps compatibility-only utilities; once service-layer
# caching returns, replace `_noop_clear_cache` with the real implementation.
