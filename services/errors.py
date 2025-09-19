"""Shared structured error payload helpers."""
from __future__ import annotations

from typing import Any, Dict, Optional


def error_payload(
    code: str,
    message: str,
    *,
    corr_id: str,
    hint: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a consistent error body for API responses."""
    payload: Dict[str, Any] = {"code": code, "message": message, "corr_id": corr_id}
    if hint:
        payload["hint"] = hint
    if extra:
        payload.update(extra)
    return payload
