# File: routes/admin_routes.py
# Purpose: Add manual trigger to generate auto global context from /context/*.md

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
import subprocess
import os

router = APIRouter(prefix="/admin", tags=["admin"])

@router.post("/generate_auto_context")
def generate_auto_context():
    try:
        result = subprocess.run(
            ["python", "scripts/generate_global_context.auto.py"],
            capture_output=True, text=True, check=True
        )
        return JSONResponse({"status": "success", "output": result.stdout})
    except subprocess.CalledProcessError as e:
        return JSONResponse(
            {"status": "error", "detail": e.stderr}, status_code=500
        )
