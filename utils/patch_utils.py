"""Utilities for working with code patches."""

from typing import Mapping, AsyncGenerator, Optional

REQUIRED_KEYS = {"type", "target_file", "patch", "reason"}


def validate_patch_format(patch: Mapping[str, object]) -> bool:
    """Return True if the mapping has all required patch keys."""
    if not isinstance(patch, Mapping):
        return False
    return REQUIRED_KEYS.issubset(patch.keys())


async def stream(message: str, context: str, user_id: Optional[str] = None) -> AsyncGenerator[str, None]:
    """Re-export codex_agent.stream for backward compatibility."""
    from agents.codex_agent import stream as codex_stream

    async for chunk in codex_stream(message, context, user_id):
        yield chunk
