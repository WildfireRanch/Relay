from fastapi import APIRouter, Depends, Header, HTTPException, Body
from pathlib import Path
import os

router = APIRouter(prefix="/control", tags=["control"])

def auth(key: str = Header(..., alias="X-API-Key")):
    if key != os.getenv("API_KEY"):
        raise HTTPException(401, "bad key")

@router.post("/write_file")
def write_file(data: dict = Body(...), user=Depends(auth)):
    path = data.get("path")
    content = data.get("content")
    
    if not path or not content:
        raise HTTPException(400, "Missing path or content")

    # Restrict writes to inside the repo only
    base = Path(__file__).resolve().parents[1]
    full_path = base / path
    full_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        full_path.write_text(content)
        return {
            "status": "success",
            "path": str(full_path.relative_to(base)),
            "size": len(content)
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to write file: {e}")
