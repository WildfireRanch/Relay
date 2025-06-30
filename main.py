# File: main.py — Relay backend entrypoint
from __future__ import annotations

import os  # ✅ FIXED: was missing
import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ─── Load .env if local ──────────────────────────────────────────────────────
if os.getenv("ENV", "local") == "local":
    try:
        from dotenv import load_dotenv
        load_dotenv()
        logging.info("✅ Loaded .env for local development")
    except ImportError:
        logging.warning("⚠️ python-dotenv not installed; skipping .env load")

ENV_NAME = os.getenv("ENV", "local")

# ─── Ensure clean rooted imports ─────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(PROJECT_ROOT))

# ─── Validate required env vars ──────────────────────────────────────────────
for key in ("API_KEY", "OPENAI_API_KEY"):
    if not os.getenv(key):
        logging.error(f"❌ Missing required env var: {key}")

# ─── Ensure docs directories exist ───────────────────────────────────────────
for sub in ("docs/imported", "docs/generated"):
    (PROJECT_ROOT / sub).mkdir(parents=True, exist_ok=True)

# ─── Initialize FastAPI app ──────────────────────────────────────────────────
app = FastAPI(
    title="Relay Command Center",
    version="1.0.0",
    description="Backend API for Relay agent – ask, control, status, docs, admin",
)

# ─── Configure CORS ──────────────────────────────────────────────────────────
cors_origins = ["*"]
allow_creds = False  # '*' requires credentials = False

override_origin = os.getenv("FRONTEND_ORIGIN")
if override_origin:
    cors_origins = [o.strip() for o in override_origin.split(",") if o.strip()]
    allow_creds = True
    logging.info(f"🔒 CORS restricted to: {cors_origins}")
else:
    logging.warning("🔓 CORS DEBUG MODE ENABLED: allow_origins='*', allow_credentials=False")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=allow_creds,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# ─── Import and mount routers ────────────────────────────────────────────────
from routes.ask import router as ask_router
from routes.status import router as status_router
from routes.control import router as control_router
from routes.docs import router as docs_router
from routes.oauth import router as oauth_router
from routes.debug import router as debug_router
from routes.kb import router as kb_router
from routes.search import router as search_router
from routes.admin import router as admin_router
from routes.codex import router as codex_router
from routes.mcp import router as mcp_router

app.include_router(ask_router)
app.include_router(status_router)
app.include_router(control_router)
app.include_router(docs_router)
app.include_router(oauth_router)
app.include_router(debug_router)
app.include_router(kb_router)
app.include_router(search_router)
app.include_router(codex_router)
app.include_router(mcp_router)

# Admin tools
if os.getenv("ENABLE_ADMIN_TOOLS", "").strip().lower() in ("1", "true", "yes"):
    app.include_router(admin_router)
    logging.info("🛠️ Admin tools enabled")
else:
    logging.info("Admin tools disabled (ENABLE_ADMIN_TOOLS not set)")

# ─── On-startup: KB auto-reindex if needed ───────────────────────────────────
from services import kb

@app.on_event("startup")  # consider lifespan context for future versions
def ensure_kb_index():
    if not kb.index_is_valid():
        logging.warning("📚 KB index missing or invalid — triggering rebuild…")
        logging.info("Reindex result: %s", kb.api_reindex())  # ✅ safer logging
    else:
        logging.info("✅ KB index validated on startup")

# ─── Root health checks ──────────────────────────────────────────────────────
@app.get("/")
def root():
    return JSONResponse({"message": "Relay Agent is Online"})

@app.get("/health")
def health_check():
    ok = True
    details: dict[str, bool] = {}

    for key in ("API_KEY", "OPENAI_API_KEY"):
        present = bool(os.getenv(key))
        details[key] = present
        ok &= present

    for sub in ("docs/imported", "docs/generated"):
        exists = (PROJECT_ROOT / sub).exists()
        details[sub] = exists
        ok &= exists

    return JSONResponse(
        {"status": "ok" if ok else "error", "details": details},
        status_code=200 if ok else 503,
    )

@app.options("/test-cors")
def test_cors():
    return JSONResponse({"message": "CORS preflight success"})

# ─── Local development entrypoint ────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        reload=ENV_NAME == "local",
    )
