# File: services/cache.py
import hashlib, json, os
import aioredis

REDIS_URL = os.getenv("REDIS_URL","redis://localhost:6379")
_redis = None
async def get_redis():
    global _redis
    if _redis is None:
        _redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis

def key_for(namespace: str, payload: dict) -> str:
    h = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return f"relay:{namespace}:{h}"

# In services/context_injector.build_context(...)
r = await get_redis()
k = key_for("ctxpack", {"q": query, "files": files, "topics": topics})
cached = await r.get(k)
if cached: return json.loads(cached)
# …build context…
await r.setex(k, 300, json.dumps({"context": ctx, "files_used": files_used}))
