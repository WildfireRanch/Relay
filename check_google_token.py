import os
import base64

# Confirm presence
token_raw = os.getenv("GOOGLE_TOKEN_JSON")
if not token_raw:
    print("❌ GOOGLE_TOKEN_JSON not found in environment variables.")
else:
    print(f"✅ GOOGLE_TOKEN_JSON loaded ({len(token_raw)} chars)")

    try:
        decoded = base64.b64decode(token_raw.encode()).decode()
        print("🔐 Decoded token preview:")
        print(decoded[:200] + "..." if len(decoded) > 200 else decoded)

        # Optional: write to disk
        with open("frontend/sync/token.json", "w") as f:
            f.write(decoded)
        print("📄 token.json written to frontend/sync/token.json")

    except Exception as e:
        print(f"❌ Failed to decode token: {e}")
