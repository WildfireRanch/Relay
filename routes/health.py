# ──────────────────────────────────────────────────────────────────────────────
# File: routes/health.py
# Purpose: Liveness (/livez) and Readiness (/readyz) probes for Ops/Deploy
#          • /livez — simple heartbeat (no dependencies)
#          • /readyz — descriptive snapshot of runtime wiring that never crashes
#            - Auth mode: which API key family is configured
#            - CORS: env list + detected CORSMiddleware settings (if mounted)
#            - Locks: existence/writability of lock directories (no-ops outside)
#            - Index root: path + writability (docs/KB rely on this)
#            - Google stack: enabled/disabled/misconfigured without network I/O
#            - Routes: count of mounted FastAPI routes (helps detect router drift)
#
# Contract:
#   • Status code 200 when generally OK.
#   • In PROD only:
#       - 503 if API auth missing, index root not writable, or Google stack
#         is "misconfigured". A "disabled" Google stack is allowed in PROD.
#   • In non-prod: never blocks; issues listed in payload for visibility.
#
# Notes:
#   • Avoids importing heavy/optional deps except guarded (google sync module).
#   • Writes a temp touch file to test writability (then removes it).
#   • No persistent side effects; creates directories only when explicitly
#     checking writability of configured paths.
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])


# ╭──────────────────────────────────────────────────────────────────────────╮
# │ Helper Utilities                                                         │
# ╰──────────────────────────────────────────────────────────────────────────╯

def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Return environment variable value or default (no casting)."""
    v = os.getenv(name)
    return v if v is not None else default


def _writable_dir(dir_path: Path) -> bool:
    """
    Return True if directory is writable:
      • Creates directory if missing (parents=True).
      • Creates and deletes a small touch file to validate write perms.
    This is intentionally side-effecty-by-design for a health probe.
    """
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
        probe = dir_path / ".readyz.touch"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _load_json_env_or_path(name: str, fallback: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """
    Try to parse JSON from:
      1) Env var referencing a file path (if exists)
      2) Env var containing base64-encoded JSON
      3) A fallback path (if provided)
    Returns:
      • dict on success
      • {"_error": "..."} dict on format/path problems
      • None if not present and fallback missing/unreadable
    """
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

    # Not a file path; try base64 JSON
    try:
        decoded = base64.b64decode(val)
        return json.loads(decoded.decode("utf-8"))
    except Exception:
        return {"_error": f"{name}: not a path or base64 JSON"}


def _is_error_obj(obj: Any) -> bool:
    """Return True if obj looks like our error sentinel dict."""
    return isinstance(obj, dict) and "_error" in obj


def _detect_env() -> str:
    """Resolve environment label to a small set; defaults to 'dev'."""
    return (_env("ENV") or _env("APP_ENV") or "dev").lower()


def _auth_summary(env: str) -> Tuple[str, List[str]]:
    """
    Determine API auth mode.
    Returns (api_auth, present_keys):
      • api_auth ∈ {"configured", "bypassed", "missing"}
      • present_keys is the list of keys found
    """
    present = [k for k in (_env("API_KEY"), _env("RELAY_API_KEY"), _env("ADMIN_API_KEY")) if k]
    if present:
        return "configured", ["API_KEY" if _env("API_KEY") else None,
                              "RELAY_API_KEY" if _env("RELAY_API_KEY") else None,
                              "ADMIN_API_KEY" if _env("ADMIN_API_KEY") else None]
    return ("bypassed" if env != "prod" else "missing"), []


def _index_root() -> Path:
    """Resolve the index root used by docs/KB subsystems."""
    return Path(_env("INDEX_ROOT", "./data/index")).resolve()


def _token_parent_dir_from_env_or_default() -> Path:
    """
    Resolve a writable directory for the Google token file:
      • If GOOGLE_TOKEN_JSON looks like a filesystem path, use its parent.
      • If GOOGLE_TOKEN_JSON looks like base64 JSON, fall back to /data/secrets.
      • Otherwise treat as a path-like string and use its parent anyway.
    """
    raw = _env("GOOGLE_TOKEN_JSON")
    default_parent = Path("/data/secrets").resolve()
    if not raw:
        return default_parent
    p = Path(raw)
    if p.suffix.lower() == ".json" or any(ch in raw for ch in ("/", "\\")):
        return p.resolve().parent
    # Might be base64 JSON; try to decode
    try:
        json.loads(base64.b64decode(raw).decode("utf-8"))
        return default_parent
    except Exception:
        return p.resolve().parent


def _google_stack_status() -> Tuple[str, Dict[str, Any]]:
    """
    Determine Google stack readiness without network calls.

    Returns (status, detail):
      • status ∈ {"disabled", "misconfigured", "ready"}
      • detail includes:
          - reason/creds_error (when relevant)
          - creds_present (bool)
          - token_parent (path str)
          - token_parent_writable (bool)
    Policy:
      • If the google sync module is explicitly marked unavailable (SYNC_AVAILABLE_ERR),
        report "disabled".
      • If creds JSON cannot be parsed or token directory isn’t writable, "misconfigured".
      • Only when both checks pass: "ready".
    """
    try:
        from services.google_docs_sync import SYNC_AVAILABLE_ERR  # type: ignore
        if SYNC_AVAILABLE_ERR:
            return "disabled", {"reason": str(SYNC_AVAILABLE_ERR)}
    except Exception as e:
        # Module import failed entirely — treat as disabled by policy.
        return "disabled", {"reason": f"google_docs_sync import failed: {e}"}

    # Validate creds parsing and token dir writeability (no network)
    creds = _load_json_env_or_path("GOOGLE_CREDS_JSON", Path("/secrets/google-creds.json"))
    creds_ok = bool(creds) and not _is_error_obj(creds)
    token_parent = _token_parent_dir_from_env_or_default()
    token_parent_writable = _writable_dir(token_parent)

    if creds_ok and token_parent_writable:
        return "ready", {
            "creds_present": True,
            "token_parent": str(token_parent),
            "token_parent_writable": True,
        }

    detail: Dict[str, Any] = {
        "creds_present": bool(creds_ok),
        "token_parent": str(token_parent),
        "token_parent_writable": token_parent_writable,
    }
    if _is_error_obj(creds):
        detail["creds_error"] = creds.get("_error")

    return "misconfigured", detail


def _cors_env_list() -> List[str]:
    """Parse FRONTEND_ORIGINS as a comma-separated list."""
    raw = _env("FRONTEND_ORIGINS", "") or ""
    return [o.strip() for o in raw.split(",") if o.strip()]


def _cors_middleware_snapshot(app) -> Dict[str, Any]:
    """Extract CORSMiddleware options if present; otherwise report detected=False."""
    try:
        for m in getattr(app, "user_middleware", []):
            if getattr(m.cls, "__name__", "") == "CORSMiddleware":
                opts = dict(getattr(m, "options", {}) or {})
                return {
                    "detected": True,
                    "allow_origins": opts.get("allow_origins"),
                    "allow_credentials": opts.get("allow_credentials"),
                    "allow_methods": opts.get("allow_methods"),
                    "allow_headers": opts.get("allow_headers"),
                    "expose_headers": opts.get("expose_headers"),
                    "max_age": opts.get("max_age"),
                }
    except Exception:
        pass
    return {"detected": False}


def _lock_candidates() -> List[str]:
    """Return candidate lock directories to inspect."""
    c = []
    env_lock = _env("LOCK_DIR")
    if env_lock:
        c.append(env_lock)
    c.extend(["var/locks", "tmp/locks"])
    # de-dup preserving order
    seen: set[str] = set()
    out: List[str] = []
    for x in c:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _locks_report() -> Dict[str, Any]:
    """Inspect candidate lock directories for existence and writability."""
    report = []
    for cand in _lock_candidates():
        p = Path(cand)
        report.append({
            "path": str(p),
            "exists": p.exists(),
            "is_dir": p.is_dir(),
            "writable": _writable_dir(p),
            "abs": str(p.resolve()) if p.exists() else None,
        })
    return {"candidates": report}


def _routes_count(app) -> Optional[int]:
    """Count APIRoute entries (helps detect router mount drift)."""
    try:
        from fastapi.routing import APIRoute
        return sum(1 for r in app.router.routes if isinstance(r, APIRoute))
    except Exception:
        return None


# ╭──────────────────────────────────────────────────────────────────────────╮
# │ Endpoints                                                                │
# ╰──────────────────────────────────────────────────────────────────────────╯

@router.get("/livez", summary="Liveness probe")
def livez() -> Dict[str, Any]:
    """Simple heartbeat; indicates process is up and serving requests."""
    return {"ok": True, "ts": int(time.time())}


@router.get("/readyz", summary="Readiness probe")
def readyz(request: Request) -> JSONResponse:
    """
    Readiness snapshot used by deploy/ops. Descriptive and resilient:
      • Never raises; always returns JSON.
      • In prod, returns 503 for truly blocking misconfigurations.
    """
    env = _detect_env()

    # Auth mode
    api_auth, present_keys = _auth_summary(env)

    # Index root (docs/KB)
    index_root = _index_root()
    index_writable = _writable_dir(index_root)

    # Google stack (no network)
    google_status, google_detail = _google_stack_status()

    # CORS (env + mounted middleware)
    cors_env = _cors_env_list()
    cors_mw = _cors_middleware_snapshot(request.app)

    # Routes
    routes_count = _routes_count(request.app)

    # Decision: 200 vs 503 (strict only in prod)
    ok = True
    problems: List[str] = []
    if env == "prod":
        if api_auth != "configured":
            ok = False
            problems.append("auth_missing")
        if not index_writable:
            ok = False
            problems.append("index_root_not_writable")
        # "disabled" Google stack is acceptable in prod by policy.
        if google_status == "misconfigured":
            ok = False
            problems.append("google_stack_misconfigured")

    payload = {
        "ok": ok,
        "env": env,
        "service": _env("SERVICE_NAME", "relay"),
        "version": _env("RELEASE", "dev"),
        "ts": int(time.time()),
        "api_auth": api_auth,
        "auth_present_keys": [k for k in present_keys if k],  # redact values; show which families exist
        "index_root": {"path": str(index_root), "writable": index_writable},
        "google_stack": google_status,
        "details": {
            "google": google_detail,
            "cors_env_frontend_origins": cors_env,
            "cors_middleware": cors_mw,
            "routes_count": routes_count,
            "locks": _locks_report(),
        },
        "problems": problems,
    }

    # Expose KB/search knobs as top-level typed fields (not stringified env)
    try:
        payload["kb_search_timeout_s"] = float(_env("KB_SEARCH_TIMEOUT_S", "30") or "30")
    except Exception:
        payload["kb_search_timeout_s"] = 30.0
    try:
        payload["semantic_score_threshold"] = float(_env("SEMANTIC_SCORE_THRESHOLD", "0.25") or "0.25")
    except Exception:
        payload["semantic_score_threshold"] = 0.25
    try:
        payload["allow_kb_fallback"] = (
            (_env("ALLOW_KB_FALLBACK", "1") or "1") not in ("0", "false", "False")
        )
    except Exception:
        payload["allow_kb_fallback"] = True

    # ──────────────────────────────────────────────────────────────────────────
    # Change: Expose kb_roots in readiness payload
    # Why: Ops visibility for docs + index paths used by KB
    # ──────────────────────────────────────────────────────────────────────────
    try:
        docs_root = str((Path("./docs")).resolve())
        payload["kb_roots"] = {"docs_root": docs_root, "index_root": str(index_root)}
    except Exception:
        # Best effort; keep payload otherwise intact
        pass

    return JSONResponse(status_code=(200 if ok else 503), content=payload)
