# ──────────────────────────────────────────────────────────────────────────────
# File: main.py
# Purpose: FastAPI entrypoint for Relay / ASK_ECHO pipeline
#          • Production-safe defaults (timeouts, request IDs, access logs)
#          • Clean CORS (explicit origin + optional regex) + proper preflight
#          • Quiet optional-router skips; stable /Live & /Ready
#          • Treat ClientDisconnect as non-error
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import importlib
import logging
import os
import time
import uuid
import traceback
from typing import Iterable, List, Optional
from pathlib import Path

import anyio
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import ClientDisconnect

# ── Logging -------------------------------------------------------------------
logger = logging.getLogger("relay.main")

# ── Env helpers ---------------------------------------------------------------

def _parse_origins(value: Optional[str]) -> List[str]:
    """
    Parse comma/space-separated CORS origins. Returns [] if unset.
    Accepts FRONTEND_ORIGINS or $shared.FRONTEND_ORIGINS.
    """
    v = (value or "").strip()
    if not v:
        return []
    parts = [p.strip() for chunk in v.split(",") for p in chunk.split() if p.strip()]
    seen, out = set(), []
    for p in parts:
        if p not in seen:
            seen.add(p); out.append(p)
    return out


def _env(name: str, fallback: str = "") -> str:
    """Env helper with $shared.NAME fallback for legacy deployment configs."""
    return os.getenv(name) or os.getenv(f"$shared.{name}") or fallback


# ── Middlewares ---------------------------------------------------------------

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a correlation ID to each request/response."""
    async def dispatch(self, request: Request, call_next):
        cid = request.headers.get("x-corr-id") or f"{uuid.uuid4().hex[:8]}{int(time.time())%1000:03d}"
        request.state.corr_id = cid
        response = await call_next(request)
        response.headers["x-corr-id"] = cid
        return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Lightweight structured access log."""
    async def dispatch(self, request: Request, call_next):
        t0 = time.perf_counter()
        method = request.method
        path = request.url.path
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            dur_ms = int((time.perf_counter() - t0) * 1000)
            # Pull corr id safely at the end so we always have something
            cid = getattr(getattr(request, "state", None), "corr_id", "-")
            logger.info("req method=%s path=%s cid=%s status=%s dur_ms=%s",
                        method, path, cid, locals().get("status", "ERR"), dur_ms)


class TimeoutMiddleware(BaseHTTPMiddleware):
    """Per-request timeout → 504 on stall (prevents worker starvation)."""
    def __init__(self, app, timeout_s: float = 35.0):
        super().__init__(app)
        self.timeout_s = timeout_s

    async def dispatch(self, request: Request, call_next):
        response = None
        with anyio.move_on_after(self.timeout_s) as scope:
            response = await call_next(request)
        if scope.cancel_called or response is None:
            return Response("Request timeout", status_code=504)
        return response


# ── App factory (installs CORS **before** routers) ----------------------------

def create_app() -> FastAPI:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Prepare required directories early and validate writability.
        def _prepare_paths() -> None:
            project_root = Path(__file__).resolve().parents[1]
            docs_imported = project_root / "docs" / "imported"
            docs_generated = project_root / "docs" / "generated"
            index_root = Path(os.getenv("INDEX_ROOT") or ".data/index").resolve()

            # Create if missing (no-op when present)
            for p in (docs_imported, docs_generated, index_root):
                try:
                    p.mkdir(parents=True, exist_ok=True)
                except Exception:
                    # Defer to writability check error handling
                    pass

            # Check writability of index_root
            writable = False
            test_file = index_root / ".writecheck.tmp"
            try:
                with open(test_file, "w", encoding="utf-8") as fh:
                    fh.write("ok")
                test_file.unlink(missing_ok=True)
                writable = True
            except Exception:
                writable = False

            app_env = (_env("ENV") or _env("APP_ENV") or "dev").strip().lower()
            if not writable and app_env in {"prod", "production"}:
                msg = f"startup failure: index_root_not_writable path={index_root} env={app_env}"
                logger.error(msg)
                raise RuntimeError(msg)

            # Single structured info line (predictable)
            logger.info(
                "paths_ready imported=%s generated=%s index_root=%s writable=%s",
                str(docs_imported), str(docs_generated), str(index_root), writable,
            )

        _prepare_paths()

        logger.info(
            "🚦 main.py LOADED file=/app/main.py commit=%s env=%s",
            _env("GIT_COMMIT", "unknown"),
            _env("APP_ENV", "main"),
        )

        otel = _env("OTEL_EXPORTER_OTLP_ENDPOINT")
        if not otel or otel.startswith("$shared"):
            logger.warning("🟣 OpenTelemetry disabled (endpoint not configured)")

        # Best-effort KB index probe (non-fatal)
        try:
            import services.kb as kb
            if hasattr(kb, "index_is_valid"):
                logger.info("✅ KB index validated (index_is_valid=%s)", kb.index_is_valid())
        except Exception:
            # Keep startup resilient
            pass

        # routes/ inventory (best-effort)
        try:
            import pkgutil, routes  # type: ignore
            listing = [m.name for m in pkgutil.iter_modules(routes.__path__)]
            logger.info("🗂️  routes/ listing: %s", listing)
        except Exception:
            pass

        yield  # shutdown: stay quiet

    app = FastAPI(lifespan=lifespan)

    # ---- CORS HARDENING (must be before include_router) ----------------------
    env_origins = _parse_origins(_env("FRONTEND_ORIGINS"))
    single_origin = (_env("FRONTEND_ORIGIN") or "").strip()
    allow_origins = env_origins or ([single_origin] if single_origin else [])

    app_env = (_env("ENV") or _env("APP_ENV") or "dev").strip().lower()
    if not allow_origins:
        if app_env in {"prod", "production"}:
            raise RuntimeError(
                "CORS misconfiguration: FRONTEND_ORIGINS (or FRONTEND_ORIGIN) is required in prod"
            )
        allow_origins = ["http://localhost:3000"]

    logger.info("🔒 CORS allow_origins=%s app_env=%s credentials=True", allow_origins, app_env)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,                     # safe with explicit origins/regex
        allow_methods=["GET", "POST", "OPTIONS"],
        # explicit header allow-list keeps proxy chains honest; include app-specific IDs
        allow_headers=[
            "content-type",
            "authorization",
            "x-corr-id",
            "x-request-id",
            "x-user-id",
            "x-thread-id",
        ],
        expose_headers=["x-corr-id"],
        max_age=600,
    )

    # ---- Core middlewares ----------------------------------------------------
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(TimeoutMiddleware, timeout_s=float(_env("HTTP_TIMEOUT_S", "35")))

    # ---- Health --------------------------------------------------------------
    @app.get("/Live")
    def live():
        return {"ok": True}

    @app.get("/Ready")
    def ready():
        # Extend with conservative checks if needed (e.g., KB index presence).
        return {"ok": True}

    # ---- ClientDisconnect is not an error -----------------------------------
    @app.exception_handler(ClientDisconnect)
    async def _client_disconnect_handler(_: Request, __: ClientDisconnect):
        # Client dropped mid-request; keep logs clean.
        return Response(status_code=204)

    return app


app = create_app()

# ── Router inclusion (ASK_ECHO priority; optional routers warn-only) ---------

# Only the truly critical routes are mandatory.
PRIMARY_ROUTERS: Iterable[str] = (
    "routes.ask",
    "routes.mcp",
)

# Start minimal; re-enable others gradually after it boots. Failures here are logged and skipped.
SECONDARY_ROUTERS: Iterable[str] = (
    # "routes.status",
    # "routes.index",
    # "routes.integrations_github",
    "routes.kb",
    # "routes.search",
    # "routes.embeddings",
    # "routes.github_proxy",
    # "routes.oauth",
    # "routes.debug",
    # "routes.codex",
    # "routes.logs",
    # "routes.status_code",
    # "routes.webhooks_github",
    # "routes.admin",
    # "routes.logs_sessions",
    # "routes.context",
)

# Feature work-in-progress (quietly skipped if import fails)
OPTIONAL_ROUTERS = {
    "routes.control",
    "routes.docs",
    "routes.health",
    "routes.x_mirror",
}

def _include(router_path: str, *, required: bool) -> None:
    """Import and mount a router. Required modules crash on error; others log+skip."""
    try:
        module = importlib.import_module(router_path)
        router = getattr(module, "router", None)
        if router is None or not isinstance(router, APIRouter):
            msg = f"no/invalid 'router' in {router_path}"
            if required:
                raise ImportError(msg)
            logger.warning("⏭️  Router skipped (%s): %s", router_path, msg)
            return
        app.include_router(router)
        name = getattr(router, "__module__", router_path).split(".")[-1]
        logger.info("🔌 Router enabled: %s (from %s)", name, router_path)
    except Exception as e:
        if required:
            logger.exception("💥 Required router failed: %s", router_path)
            raise
        # Log full traceback but keep app alive
        logger.error("⏭️  Router skipped (%s): %s\n%s", router_path, e, traceback.format_exc())

# Mount primary first (must succeed), then tolerant passes for secondary/optional
for rp in PRIMARY_ROUTERS:
    _include(rp, required=True)
for rp in SECONDARY_ROUTERS:
    _include(rp, required=False)
for rp in OPTIONAL_ROUTERS:
    _include(rp, required=False)

logger.info("✅ Critical routers present: ['ask','mcp']")

# ── Optional: tiny debug endpoint (safe in prod) ------------------------------

@app.get("/gh/debug/api-key")
def debug_api_key() -> dict:
    """Minimal, non-sensitive sanity check for GitHub/OpenAI wiring."""
    return {
        "openai_key_present": bool(_env("OPENAI_API_KEY")),
        "github_app_id_present": bool(_env("GITHUB_APP_ID")),
    }

# ──────────────────────────────────────────────────────────────────────────────
# End of file
# ──────────────────────────────────────────────────────────────────────────────
