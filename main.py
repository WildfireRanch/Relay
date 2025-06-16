# ────────────────────────────────────────────────────────────────────────────
# File: main.py
# Directory: project root
# Purpose : FastAPI entrypoint for Relay backend.
#           Adds auto-heal KB startup hook + unified single-key security.
# Last Updated: 2025-06-15
# ────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ─── Optional .env for local dev ────────────────────────────────────────────
if os.getenv("ENV", "local") == "local":
    try:
        from dotenv import load_dotenv
        load_dotenv()
        logging.info("Loaded .env for local development")
    except ImportError:
        logging.warning("python-dotenv not installed; skipping .env load")

ENV_NAME = os.getenv("ENV", "local")

# ─── Basic env validation (extend as needed) ───────────────────────────────
for key in ("API_KEY", "OPENAI_API_KEY"):
    if not os.getenv(key):
        logging.error("Missing env var: %s", key)

PROJECT_ROOT = Path(__file__).resolve().parent
for sub in ("docs/imported", "docs/generated"):
    (PROJECT_ROOT / sub).mkdir(parents=True, exist_ok=True)

# ─── FastAPI setup ─────────────────────────────────────────────────────────
app = FastAPI(
    title="Relay Command Center",
    version="1.0.0",
    description="Backend for Relay agent: ask, status, control, docs, KB, admin",
)

# ─── CORS (unchanged) ──────────────────────────────────────────────────────
# … existing CORS block …

# ─── Router imports (unchanged) ────────────────────────────────────────────
# … existing router imports …
from routes.kb import router as kb_router
# etc.

# ─── Register routers (unchanged) ──────────────────────────────────────────
# … app.include_router(...) list …

# ─── Auto-heal KB on startup ───────────────────────────────────────────────
from services import kb  # after routers so imports resolve

@app.on_event("startup")
def ensure_kb_index():
    """
    Build/rebuild the KB index automatically if:
      • missing     – first boot on a fresh volume
      • mismatched  – vector dimension ≠ model spec (env drift)
    """
    if not kb.index_is_valid():
        logging.warning("KB index invalid or missing → rebuilding…")
        res = kb.api_reindex()
        logging.info("KB rebuild complete: %s", res)
    else:
        logging.info("KB index valid — no rebuild needed")

# ─── Root & health endpoints (unchanged) ───────────────────────────────────
# … existing root() and health_check() …

# ─── Local dev entrypoint (unchanged) ──────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        reload=ENV_NAME == "local",
    )
