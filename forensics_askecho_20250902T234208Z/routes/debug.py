# ──────────────────────────────────────────────────────────────────────────────
# File: debug.py
# Directory: routes
# Purpose: # Purpose: Provides an API endpoint to display current environment settings for debugging purposes.
#
# Upstream:
#   - ENV: GOOGLE_CREDS_JSON
#   - Imports: fastapi, os
#
# Downstream:
#   - main
#
# Contents:
#   - debug_env()

# ──────────────────────────────────────────────────────────────────────────────

from fastapi import APIRouter
import os

router = APIRouter()

@router.get("/debug/env")
def debug_env():
    val = os.getenv("GOOGLE_CREDS_JSON")
    return {
        "GOOGLE_CREDS_JSON present": bool(val),
        "length": len(val) if val else 0,
        "starts_with": val[:30] + "..." if val else "MISSING"
    }
