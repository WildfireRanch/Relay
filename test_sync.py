# File: test_sync.py
import requests

RELAY_URL = "https://relay.wildfireranch.us/docs/full_sync"

try:
    print(f"🔄 Triggering sync at: {RELAY_URL}")
    response = requests.post(RELAY_URL, timeout=30)
    print(f"✅ Status Code: {response.status_code}")
    print(f"📦 Response: {response.json()}")
except Exception as e:
    print(f"❌ Sync failed: {e}")
