# routes/github_proxy.py (top of file)
import os, hmac
from fastapi import APIRouter, Depends, Header, HTTPException
...
router = APIRouter(prefix="/gh", tags=["github"])

# Allow one or more keys via comma-separated env var
_API_KEYS = {tok.strip() for tok in os.getenv("API_KEY", "").split(",") if tok.strip()}
if not _API_KEYS:
    # Optional: fall back to API_KEYS env for compatibility
    _API_KEYS = {tok.strip() for tok in os.getenv("API_KEYS", "").split(",") if tok.strip()}

def require_api_key(authorization: str = Header(None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    for k in _API_KEYS:
        if hmac.compare_digest(token, k):
            return  # authorized
    raise HTTPException(status_code=403, detail="Bad token")

# Optional debug (remove after verifying)
@router.get("/debug/api-key")
def gh_debug_api_key(authorization: str | None = Header(None)):
    import hashlib
    def sha8(s: str) -> str: return hashlib.sha256(s.encode()).hexdigest()[:8]
    provided = ""
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization.split(" ", 1)[1].strip()
    server_key = next(iter(_API_KEYS), "")
    return {
        "server_key_len": len(server_key),
        "server_key_sha256_8": sha8(server_key) if server_key else None,
        "provided_len": len(provided),
        "provided_sha256_8": sha8(provided) if provided else None,
        "match": any(hmac.compare_digest(provided, k) for k in _API_KEYS),
        "keys_count": len(_API_KEYS),
    }
