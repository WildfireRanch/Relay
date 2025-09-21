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

# ──────────────────────────────────────────────────────────────────────────────
# Change: Quiet noisy libs in production logs
# Why: Cleaner logs (no framework warnings, no per-request httpx spam)
# ──────────────────────────────────────────────────────────────────────────────
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.ERROR)


# ──────────────────────────────────────────────────────────────────────────────
# LlamaIndex LLM defaults (chat model, retries, timeout)
# Why: Avoid legacy gpt-3.5-turbo RPD caps; set sane retries/timeouts centrally
# ──────────────────────────────────────────────────────────────────────────────
try:
    from llama_index.core import Settings as LI_Settings  # type: ignore
    from llama_index.llms.openai import OpenAI as LI_OpenAI  # type: ignore
    from llama_index.embeddings.openai import OpenAIEmbedding  # type: ignore
    import os

    CHAT_MODEL = os.getenv("LLM_CHAT_MODEL", "gpt-4o-mini")
    CHAT_MAX_RETRIES = int(os.getenv("LLM_CHAT_MAX_RETRIES", "1"))
    CHAT_TIMEOUT_S = float(os.getenv("LLM_CHAT_TIMEOUT_S", "30"))
    EMB_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")

    LI_Settings.llm = LI_OpenAI(model=CHAT_MODEL, max_retries=CHAT_MAX_RETRIES, timeout=CHAT_TIMEOUT_S)
    # Keep current embedding model; this matches your services.kb logs
    LI_Settings.embed_model = OpenAIEmbedding(model=EMB_MODEL)
    logger.info("🔧 LlamaIndex configured llm=%s retries=%s timeout_s=%.1f embed=%s",
                CHAT_MODEL, CHAT_MAX_RETRIES, CHAT_TIMEOUT_S, EMB_MODEL)
except Exception as _e:
    logger.warning("LlamaIndex not configured (%s)", _e)

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
    """Per-request timeout with a longer budget for known long operations.

    Default: 35s (HTTP_TIMEOUT_S). Long ops: LONG_OP_TIMEOUT_S (default 300s).
    Long ops are matched by path startswith against LONG_OP_PATHS.
    """
    def __init__(self, app, timeout_s: float = 35.0):
        super().__init__(app)
        self.default_timeout = timeout_s
        # Comma-separated, defaults cover our KB/docs heavy endpoints
        paths = os.getenv(
            "LONG_OP_PATHS",
            "/docs/refresh_kb,/docs/sync,/docs/full_sync,/kb/reindex"
        )
        self.long_op_paths = tuple(p.strip() for p in paths.split(",") if p.strip())
        self.long_timeout = float(os.getenv("LONG_OP_TIMEOUT_S", "300"))

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        budget = self.long_timeout if path.startswith(self.long_op_paths) else self.default_timeout
        response = None
        with anyio.move_on_after(budget) as scope:
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
    # Make these fail-soft so the app stays up while we diagnose imports.
    "routes.docs",
    "routes.kb",
)

OPTIONAL_ROUTERS = {
    "routes.control",
    "routes.x_mirror",
    # GitHub integrations (API + proxy + webhooks)
    "routes.integrations_github",
    "routes.github_proxy",
    "routes.webhooks_github",
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
# ║ Router map (read-only; safe for ops)                                     ║
# ╚══════════════════════════════════════════════════════════════════════════╝

@app.get("/__router_map")
def router_map(
    prefix: str = "",              # optional: return only paths starting with this
    tag: str | None = None,        # optional: filter by a specific tag
    method: str | None = None,     # optional: filter by HTTP method (e.g., GET)
    regex: str | None = None,      # optional: re filter on path (compiled safely)
    verbose: int = 0,              # optional: include extra fields when 1
):
    """
    Read-only inventory of mounted routes (paths + methods).
    Filters:
      • prefix=/docs     → only routes starting with /docs
      • tag=docs         → only routes carrying the 'docs' tag
      • method=POST      → only routes exposing that method
      • regex=^/kb/.*    → only routes whose path matches this regex
      • verbose=1        → include name, module, tags, and auth hint

    Guaranteed to never raise; returns {"routes":[...],"count":N,"filters":{...}}
    """
    try:
        import re
        from fastapi.routing import APIRoute
    except Exception as e:
        return {"error": f"imports failed: {e}"}

    # Compile regex safely, but do not fail the endpoint if it's invalid
    rx = None
    if regex:
        try:
            rx = re.compile(regex)
        except Exception:
            rx = None  # ignore invalid regex; behave as if unset

    def _has_api_key_dep(r: APIRoute) -> bool:
        """
        Best-effort detection of our shared API-key dependency.
        Never raises; returns False if structure changes.
        """
        try:
            dep = getattr(r, "dependant", None)
            if not dep:
                return False
            for d in getattr(dep, "dependencies", []) or []:
                call = getattr(d, "call", None)
                # Match by function name to avoid import coupling
                if getattr(call, "__name__", "") == "require_api_key":
                    return True
        except Exception:
            return False
        return False

    rows = []
    try:
        for r in app.router.routes:  # type: ignore[attr-defined]
            if not isinstance(r, APIRoute):
                continue
            path = r.path
            methods = sorted(list(r.methods or []))

            # Basic filters (fast)
            if prefix and not path.startswith(prefix):
                continue
            if method and method.upper() not in methods:
                continue

            # Tag filter (APIRoute.tags is a list[str], may be absent)
            rtags = []
            try:
                rtags = list(getattr(r, "tags", []) or [])
            except Exception:
                rtags = []
            if tag and tag not in rtags:
                continue

            # Regex filter last (slowest)
            if rx and not rx.search(path or ""):
                continue

            item = {
                "path": path,
                "methods": methods,
            }

            if verbose:
                # Extra fields for ops
                try:
                    item["name"] = getattr(r, "name", None)
                except Exception:
                    item["name"] = None
                try:
                    # endpoint is the user function; module gives provenance
                    ep = getattr(r, "endpoint", None)
                    item["module"] = getattr(ep, "__module__", None)
                except Exception:
                    item["module"] = None
                item["tags"] = rtags
                item["auth_api_key"] = _has_api_key_dep(r)

            rows.append(item)

        rows.sort(key=lambda x: (x["path"], ",".join(x["methods"])))
        return {
            "routes": rows,
            "count": len(rows),
            "filters": {"prefix": prefix or None, "tag": tag, "method": (method.upper() if method else None), "regex": regex, "verbose": bool(verbose)},
        }
    except Exception as e:
        # Last-resort guard (never crash)
        return {"routes": [], "count": 0, "filters": {"prefix": prefix or None, "tag": tag, "method": method, "regex": regex, "verbose": bool(verbose)}, "error": str(e)}

# ── Router diagnostics: attempt imports and report exceptions (read-only) -----
@app.get("/__router_diag")
def __router_diag():
    """
    Attempts to import key route modules and returns exception strings, if any.
    Does NOT mount anything; purely diagnostic for ops.
    """
    import importlib, traceback
    targets = ["routes.docs", "routes.kb", "routes.x_mirror"]
    out = {}
    for mod in targets:
        try:
            importlib.reload(importlib.import_module(mod))
            out[mod] = {"ok": True}
        except Exception as e:
            out[mod] = {
                "ok": False,
                "error": f"{e.__class__.__name__}: {e}",
                "traceback": traceback.format_exc(),
            }
    return {"diagnostics": out}
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
