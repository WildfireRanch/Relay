# Relay

Relay is a FastAPI backend used to sync Google Docs into Markdown files and serve them to the frontend. The project relies on Google OAuth to read documents from a Drive folder.

---

## Google Docs Sync

The sync service requires a Google OAuth client and (optionally) an existing token. Configuration is handled via environment variables:

| Variable | Purpose |
|----------|---------|
| `GOOGLE_CREDS_JSON` | Base64-encoded contents of your Google client-secret JSON |
| `GOOGLE_TOKEN_JSON` | Base64-encoded OAuth token JSON from a prior login (optional) |
| `ENV`               | Set to `local` when running interactively so OAuth can open a browser |

### OAuth Flow

1. Start authentication by visiting `/google/auth` in your running instance.  
2. After granting access, Google redirects to `/google/callback`, which stores `frontend/sync/token.json` for future requests.

### Manual Authorization

```bash
python scripts/authorize_google.py
```

The script prints a URL, prompts for the returned code, and then writes the token to `frontend/sync/token.json`.

---

## Example `.env`

```dotenv
# ── Google OAuth ──────────────────────────
GOOGLE_CREDS_JSON=
GOOGLE_TOKEN_JSON=

# ── OpenAI / Relay core ───────────────────
OPENAI_API_KEY=
API_KEY=relay-dev         # single key for all protected routes

# ── CORS override (optional) ──────────────
# FRONTEND_ORIGIN=https://my.custom.frontend

# ── Runtime ───────────────────────────────
ENV=local
```

---

## 🚦 CORS / Front-End Access

FastAPI’s `CORSMiddleware` is pre-configured; just set the correct env and **make sure your edge proxy forwards the `OPTIONS` verb**.

| ENV (`ENV` var)  | Allowed Origins (default)                                | Credentials |
|------------------|----------------------------------------------------------|-------------|
| `local`, `prod`  | https://relay.wildfireranch.us, https://status.wildfireranch.us, http://localhost:3000 <br>*(override by setting `FRONTEND_ORIGIN` to a comma-separated list)* | ✅ |
| `staging`, `preview` | `*` (wildcard) | ❌ |

**Custom headers**  
`X-API-Key` and `X-User-Id` are explicitly whitelisted, so browser calls to protected routes won’t fail the CORS pre-flight.

**Edge rule (one-time setup)**  
Add `OPTIONS` to the allowed HTTP methods in Railway “Edge Rules” (or Cloudflare, if used). Once set, no further action is required.

### Quick smoke test

```bash
curl -X OPTIONS https://relay.wildfireranch.us/kb/search \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: POST" \
  -I
# Expect: HTTP/2 200 + Access-Control-Allow-* headers
```

---

*Last updated: 2025-06-16*
