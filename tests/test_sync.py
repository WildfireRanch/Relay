# File: test_sync.py
import json
from urllib import request, error

RELAY_URL = "https://relay.wildfireranch.us/docs/full_sync"

try:
    print(f"🔄 Triggering sync at: {RELAY_URL}")
    req = request.Request(RELAY_URL, method="POST")
    with request.urlopen(req, timeout=30) as res:
        status = res.getcode()
        body = res.read()
        try:
            body_json = json.loads(body)
        except Exception:
            body_json = body.decode()
        print(f"✅ Status Code: {status}")
        print(f"📦 Response: {body_json}")
except Exception as e:
    print(f"❌ Sync failed: {e}")
