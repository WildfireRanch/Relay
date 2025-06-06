# File: routes/debug.py
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
