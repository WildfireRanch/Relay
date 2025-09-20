# ──────────────────────────────────────────────────────────────────────────────
# File: main.py
# Purpose: FastAPI entrypoint for Relay / ASK_ECHO pipeline
#
# Guarantees
#   • Production-safe defaults: request IDs, gzip, access logs, timeouts.
#   • Single-source CORS (FRONTEND_ORIGINS) with solid preflight behavior.
#   • Health endpoints mounted EARLY and ALWAYS available (/livez, /readyz).
#   • Required routers fail-fast; optional routers fail-soft (log + continue).
#   • ClientDisconnect is not treated as an application error.
#
# Notes
#   • INDEX_ROOT defaults to ./data/index (created & probed for writability).
#   • FRONTEND_ORIGINS must be set in prod; dev falls back to localhost:3000.
#   • Keep this file small and boring; complex logic belongs in services/.
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

# ── Stdlib --------------------------------------------------------------------
import importlib
import logging
import os
import time
import traceback
import uuid
from pathlib import Path
from typing import Iterable, List, Optional

# ── Third-party ---------------------------------------------------------------
import anyio
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import ClientDisconnect

# ── Logging -------------------------------------------------------------------
logger = logging.getLogger("relay.main")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ Environment Helpers                                                      ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _env(name: str, fallback: str = "") -> str:
    """
    Read an environment variable with optional legacy "$shared.NAME" fallback.

    Avoid casting here—keep values as strings; cast in the consumer.
    """
    return os.getenv(name) or os.getenv(f"$shared.{name}") or fallback


def _parse_origins(value: Optional[str]) -> List[str]:
    """
    Parse FRONTEND_ORIGINS into a unique, ordered list.

    Accepts comma or whitespace separation. Returns [] if unset.
    """
    v = (value or "").strip()
    if not v:
        return []
    parts = [p.strip() for chunk in v.split(",") for p in chunk.split() if p.strip()]
    seen, out = set(), []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ Middlewares                                                              ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Attach a correlation ID to each request and echo it in the response headers.

    Header: X-Corr-Id (in/out)
    """
    async def dispatch(self, request: Request, call_next):
        cid = request.headers.get("x-corr-id") or f"{uuid.uuid4().hex[:8]}{int(time.time())%1000:03d}"
        request.state.corr_id = cid
        response = await call_next(request)
        response.headers["x-corr-id"] = cid
        return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    """
    Minimal structured access log. Always logs a line, even on exceptions.

    Fields: method, path, cid, status, dur_ms
    """
    async def dispatch(self, request: Request, call_next):
        t0 = time.perf_counter()
        method = request.method
        path = request.url.path
        status = None
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            dur_ms = int((time.perf_counter() - t0) * 1000)
            cid = getattr(getattr(request, "state", None), "corr_id", "-")
            logger.info(
                "req method=%s path=%s cid=%s status=%s dur_ms=%s",
                method, path, cid, status if status is not None else "ERR", dur_ms
            )


class TimeoutMiddleware(BaseHTTPMiddleware):
    """
    Per-request timeout to prevent worker starvation.

    Returns 504 when the handler exceeds timeout_s.
    """
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


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ App Factory (Lifespan, CORS, Health, Middlewares)                        ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def create_app() -> FastAPI:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """
        Startup: prepare directories, validate writability, print minimal inventory.
        Shutdown: quiet.
        """
        def _prepare_paths() -> None:
            project_root = Path(__file__).resolve().parents[1]
            docs_imported = project_root / "docs" / "imported"
            docs_generated = project_root / "docs" / "generated"
            index_root = Path(_env("INDEX_ROOT") or "./data/index").resolve()

            # Create if missing (no-op when present)
            for p in (docs_imported, docs_generated, index_root):
                try:
                    p.mkdir(parents=True, exist_ok=True)
                except Exception:
                    # Defer to writability probe
                    pass

            # Writability probe for index_root (touch + remove)
            writable = False
            try:
                test_file = index_root / ".writecheck.tmp"
                test_file.write_text("ok", encoding="utf-8")
                test_file.unlink(missing_ok=True)
                writable = True
            except Exception:
                writable = False

            app_env = (_env("ENV") or _env("APP_ENV") or "dev").strip().lower()
            if not writable and app_env in {"prod", "production"}:
                msg = f"startup failure: index_root_not_writable path={index_root} env={app_env}"
                logger.error(msg)
                raise RuntimeError(msg)

            logger.info(
                "paths_ready imported=%s generated=%s index_root=%s writable=%s",
                str(docs_imported), str(docs_generated), str(index_root), writable,
            )

        _prepare_paths()

        logger.info(
            "🚦 main.py LOADED file=/app/main.py commit=%s env=%s",
            _env("GIT_COMMIT", "unknown"),
            _env("APP_ENV", "dev"),
        )

        # Optional telemetry hint
        otel = _env("OTEL_EXPORTER_OTLP_ENDPOINT")
        if not otel or otel.startswith("$shared"):
            logger.warning("🟣 OpenTelemetry disabled (endpoint not configured)")

        # Best-effort KB index probe (non-fatal)
        try:
            import services.kb as kb  # type: ignore
            if hasattr(kb, "index_is_valid"):
                logger.info("✅ KB index validated (index_is_valid=%s)", kb.index_is_valid())
        except Exception:
            pass

        # routes/ inventory (best-effort)
        try:
            import pkgutil, routes  # type: ignore
            listing = [m.name for m in pkgutil.iter_modules(routes.__path__)]
            logger.info("🗂️  routes/ listing: %s", listing)
        except Exception:
            pass

        yield

    # FastAPI app with lifespan manager
    app = FastAPI(lifespan=lifespan)

    # ── CORS (MUST be before include_router) ----------------------------------
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
        allow_credentials=True,  # safe with explicit origins
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "content-type",
            "authorization",
            "x-api-key",   # allow API key for browser preflight success
            "x-corr-id",
            "x-request-id",
            "x-user-id",
            "x-thread-id",
        ],
        expose_headers=["x-corr-id"],
        max_age=600,
    )

    # ── Core Middlewares -------------------------------------------------------
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(TimeoutMiddleware, timeout_s=float(_env("HTTP_TIMEOUT_S", "35")))

    # ── Health (mount EARLY and ALWAYS) ---------------------------------------
    try:
        from routes.health import router as health_router  # /livez, /readyz
        app.include_router(health_router)
        logger.info("🔌 Router enabled early: health (/livez, /readyz)")
    except Exception as e:
        logger.exception("💥 Failed to mount health router: %s", e)
        raise

    # ── ClientDisconnect is not an error --------------------------------------
    @app.exception_handler(ClientDisconnect)
    async def _client_disconnect_handler(_: Request, __: ClientDisconnect):
        # Client dropped mid-request; keep logs clean.
        return Response(status_code=204)

    return app


# Instantiate the app (used by ASGI server)
app = create_app()


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ Router Inclusion                                                         ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# Strategy:
#   • PRIMARY_ROUTERS must succeed; raise on failure (fail-fast).
#   • SECONDARY_ROUTERS are recommended; log + continue on failure.
#   • OPTIONAL_ROUTERS are experimental/nice-to-have; log + continue on failure.

PRIMARY_ROUTERS: Iterable[str] = (
    "routes.ask",
    "routes.mcp",
)

SECONDARY_ROUTERS: Iterable[str] = (
    "routes.kb",
)

OPTIONAL_ROUTERS = {
    "routes.control",
    "routes.docs",      # docs UI + sync endpoints
    "routes.x_mirror",
    # NOTE: routes.health is mounted early above; do not mount it again.
}

def _include(router_path: str, *, required: bool) -> None:
    """
    Import and mount a router by module path.

    • required=True → raises on any error (service should not run without it)
    • required=False → logs full traceback and continues
    """
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
        logger.error("⏭️  Router skipped (%s): %s\n%s", router_path, e, traceback.format_exc())


# Mount primary first (must succeed), then tolerant passes for secondary/optional
for rp in PRIMARY_ROUTERS:
    _include(rp, required=True)
for rp in SECONDARY_ROUTERS:
    _include(rp, required=False)
for rp in OPTIONAL_ROUTERS:
    _include(rp, required=False)

logger.info("✅ Critical routers present: ['ask','mcp']")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ Tiny Debug Endpoint (Safe)                                               ║
# ╚══════════════════════════════════════════════════════════════════════════╝

@app.get("/gh/debug/api-key")
def debug_api_key() -> dict:
    """
    Minimal, non-sensitive sanity check for GitHub/OpenAI wiring.
    (Helps verify env var presence without leaking secrets.)
    """
    return {
        "openai_key_present": bool(_env("OPENAI_API_KEY")),
        "github_app_id_present": bool(_env("GITHUB_APP_ID")),
    }


# ──────────────────────────────────────────────────────────────────────────────
# End of file
# ──────────────────────────────────────────────────────────────────────────────
