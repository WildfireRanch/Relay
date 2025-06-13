# File: main.py
# Directory: project root
# Purpose: Relay backend FastAPI application (runtime‑only indexing, unified KB search, admin endpoints)
# Notes:
#   • Loads `.env` **only** when ENV=local (Codespaces/CI secrets stay off‑disk)
#   • CORS origins configurable via FRONTEND_ORIGIN env (fallback list for prod/staging)
#   • Removes legacy routes/embeddings import – all search goes through routes.search → services.kb
#   • Registers /admin/reindex (API‑key protected) for on‑demand KB rebuild
# Last Updated: 2025‑06‑12

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ─── Optional .env loading (local‑only) ─────────────────────────────────────
if os.getenv("ENV", "local") == "local":
    try:
        from dotenv import load_dotenv
        load_dotenv()
        logging.info("Loaded .env for local development")
    except ImportError:
        logging.warning("python‑dotenv not installed; skipping .env load")

# ─── Validate essential env vars ───────────────────────────────────────────
required_env = [
    "API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_CREDS_JSON",
]
missing = [k for k in required_env if not os.getenv(k)]
if missing:
    logging.error("Missing required env vars: %s", missing)
else:
    logging.info("✅ Required environment variables present")

# ─── Ensure docs directories exist ────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
for sub in ["docs/imported", "docs/generated"]:
    path = PROJECT_ROOT / sub
    path.mkdir(parents=True, exist_ok=True)
    logging.debug("Ensured directory %s", path)

# ─── FastAPI application setup ─────────────────────────────────────────────
app = FastAPI(
    title="Relay Command Center",
    version="1.0.0",
    description="Backend for Relay agent: ask, status, control, docs, oauth, KB, admin",
)

# ─── CORS ──────────────────────────────────────────────────────────────────
frontend_origins = os.getenv("FRONTEND_ORIGIN")
if frontend_origins:
    origins = [o.strip() for o in frontend_origins.split(",") if o.strip()]
else:
    origins = [
        "https://relay.wildfireranch.us",
        "https://status.wildfireranch.us",
        "https://relay.staging.wildfireranch.us",
        "https://status.staging.wildfireranch.us",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logging.info("CORS configured for origins: %s", origins)

# ─── Router imports ───────────────────────────────────────────────────────
from routes.ask import router as ask_router
from routes.status import router as status_router
from routes.control import router as control_router
from routes.docs import router as docs_router
from routes.oauth import router as oauth_router
from routes.debug import router as debug_router
from routes.kb import router as kb_router               # native KB endpoints
from routes.search import router as search_router       # proxy to services.kb
from routes import admin as admin_router                # admin utilities

# Legacy `routes.embeddings` removed – all search unified via routes.search

# ─── Register routers ─────────────────────────────────────────────────────
app.include_router(ask_router)
app.include_router(status_router)
app.include_router(control_router)
app.include_router(docs_router)
app.include_router(oauth_router)
app.include_router(debug_router)
app.include_router(kb_router)
app.include_router(search_router)
app.include_router(admin_router.router)   # /admin/reindex etc.

logging.info("✅ All route modules registered (legacy embeddings route deprecated)")

# ─── Health & root endpoints ───────────────────────────────────────────────
@app.get("/", summary="Health check")
def root():
    """Liveness endpoint for load balancers/UptimeRobot."""
    return JSONResponse({"message": "Relay Agent is Online"})


@app.get("/health", summary="Readiness probe")
def health_check():
    """Verifies essential env vars and docs directories exist."""
    ok = True
    details: dict[str, bool] = {}

    for key in required_env:
        present = bool(os.getenv(key))
        details[key] = present
        ok = ok and present

    for sub in ["docs/imported", "docs/generated"]:
        exists = (PROJECT_ROOT / sub).exists()
        details[sub] = exists
        ok = ok and exists

    return JSONResponse({"status": "ok" if ok else "error", "details": details}, status_code=(200 if ok else 503))

# ─── Local dev entrypoint ─────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        reload=os.getenv("ENV", "local") == "local",
    )
