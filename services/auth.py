from __future__ import annotations

import os
from typing import Optional, Dict, Any

from fastapi import Header, HTTPException, status


# Helpers
def _env(name: str) -> Optional[str]:
    return os.getenv(name) or os.getenv(f"$shared.{name}")


def _valid_keys() -> Dict[str, str]:
    return {
        k: v
        for k, v in {
            "ADMIN_API_KEY": _env("ADMIN_API_KEY"),
            "RELAY_API_KEY": _env("RELAY_API_KEY"),
            "API_KEY": _env("API_KEY"),
        }.items()
        if v
    }


def _extract_token(x_api_key: Optional[str], authorization: Optional[str]) -> Optional[str]:
    if x_api_key:
        return x_api_key.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


# FastAPI Dependency
async def require_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-Api-Key"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> Dict[str, Any]:
    """
    Validate API key from `X-Api-Key` header or `Authorization: Bearer ...`.
    Returns a small auth context on success; raises 401/403 on failure.
    """
    token = _extract_token(x_api_key, authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key (provide X-Api-Key or Authorization: Bearer <token>)",
        )

    keys = _valid_keys()
    for family, expected in keys.items():
        if token == expected:
            return {"ok": True, "family": family}

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid API key",
    )

