# File: services/contextinjector.py
# Purpose: Back-compat shim; logic moved into core.context_engine.
from core.context_engine import (
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