# File: services/contextengine.py
# Purpose: Back-compat shim during Phase 2 → Phase 3.
from core.context_engine import (  # re-export
    build_context,
    ContextRequest,
    EngineConfig,
    RetrievalTier,
    Retriever,
    ContextResult,
)
__all__ = [
    "build_context",
    "ContextRequest",
    "EngineConfig",
    "RetrievalTier",
    "Retriever",
    "ContextResult",
]
# Note: No other code here to avoid circularity with core/context_engine.py