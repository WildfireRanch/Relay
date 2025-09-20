# ──────────────────────────────────────────────────────────────────────────────
# File: routes/health.py
# Purpose: Lightweight readiness probe for Ops/Deploy checks
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])

# ─── Helpers ──────────────────────────────────────────────────────────────────
def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    return v if v is not None else default

def _writable(p: Path) -> bool:
    try:
        p.mkdir(parents=True, exist_ok=True)
        test = p / ".readyz.touch"
        test.write_text("ok", encoding="utf-8")
        test.unlink(missing_ok=True)
        return True
    except Exception:
        return False

def _load_json_env_or_path(name: str, fallback: Path | None = None) -> Dict[str, Any] | None:
    """Return dict if value resolves; None if unset and no fallback."""
    val = _env(name)
    if not val and fallback:
        try:
            return json.loads(fallback.read_text(encoding="utf-8"))
        except Exception:
            return None
    if not val:
        return None
    p = Path(val)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {"_error": f"{name}: invalid JSON file"}
    # base64 JSON?
    import base64
    try:
        return json.loads(base64.b64decode(val).decode("utf-8"))
    except Exception:
        return {"_error": f"{name}: not a path or base64 JSON"}

# ─── Readiness Route ──────────────────────────────────────────────────────────
@router.get("/readyz")
def readyz():
    env = (_env("ENV") or _env("APP_ENV") or "dev").lower()
    # Auth
    keys = [k for k in (_env("API_KEY"), _env("RELAY_API_KEY"), _env("ADMIN_API_KEY")) if k]
    api_auth = "configured" if keys else ("bypassed" if env != "prod" else "missing")

    # Index root
    index_root = Path(_env("INDEX_ROOT", "./data/index")).resolve()
    index_writable = _writable(index_root)

    # Google stack
    google_status: str
    google_detail: Dict[str, Any] | None = None
    try:
        from services.google_docs_sync import SYNC_AVAILABLE_ERR  # type: ignore
        if SYNC_AVAILABLE_ERR:
            google_status = "disabled"
            google_detail = {"reason": str(SYNC_AVAILABLE_ERR)}
        else:
            # Validate creds load (does not hit network)
            creds = _load_json_env_or_path("GOOGLE_CREDS_JSON", Path("/secrets/google-creds.json"))
            token_parent = Path((_env("GOOGLE_TOKEN_JSON") or "/data/secrets/google-token.json")).resolve().parent
            google_status = "ready" if (creds and _writable(token_parent)) else "misconfigured"
            google_detail = {
                "creds_present": bool(creds),
                "token_parent_writable": _writable(token_parent),
            }
    except Exception as e:
        # Module import failed entirely (no guarded file) — treat as disabled.
        google_status = "disabled"
        google_detail = {"reason": str(e)}

    ok = True
    problems: list[str] = []

    if env == "prod":
        if api_auth != "configured":
            ok = False
            problems.append("auth_missing")
        if not index_writable:
            ok = False
            problems.append("index_root_not_writable")
        # google_status may be "disabled" in prod if you consciously run without sync.
        # Treat "misconfigured" as a failure; "disabled" is acceptable by policy.
        if google_status == "misconfigured":
            ok = False
            problems.append("google_stack_misconfigured")

    status = {
        "ok": ok,
        "env": env,
        "api_auth": api_auth,
        "index_root": {"path": str(index_root), "writable": index_writable},
        "google_stack": google_status,
        "details": {"google": google_detail},
        "problems": problems,
    }
    code = 200 if ok else 503
    return JSONResponse(status_code=code, content=status)
