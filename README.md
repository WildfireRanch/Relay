# 🤠 Relay Command Center – Readme

> Cloud-native, agent-powered AI control system with semantic doc search, human-in-the-loop patching, and Google Docs sync.

---

## 🚀 Features

* GPT-4o-powered agent with patch suggestions and approval
* Semantic search using LlamaIndex + OpenAI embeddings
* Modular frontend (Next.js) and backend (FastAPI)
* Google Docs → Markdown sync with OAuth 2.0
* Secure, secretless deployment via Railway and Vercel
* CORS-aware, audit-logged API with per-env controls

---

## 👭 System Architecture

```
[ Next.js SPA (Vercel) ]
        ⇅ SSO + API
[ FastAPI Backend (Railway) ]
        ⇅ REST API
[ Semantic Index (LlamaIndex + OpenAI) ]
        ⇅
[ Markdown Docs (/docs/imported) ]
```

* Frontend: `frontend/`
* Backend: `main.py`, `routes/`, `services/`
* Docs: `/docs/imported/`, `/docs/generated/`
* Index: `data/index/<env>/<model>/`
* Audit Log: `logs/audit.jsonl`

---

## 🔐 Environment Variables (Quick Reference)

For full details, see [`/docs/PROJECT_SUMMARY.md`](./docs/PROJECT_SUMMARY.md)

| Variable                 | Scope    | Purpose                                                    |
| ------------------------ | -------- | ---------------------------------------------------------- |
| `ENV`                    | Backend  | `local`, `develop`, `main` for env-specific logic          |
| `API_KEY`                | Backend  | Master API key for protected endpoints                     |
| `ENABLE_ADMIN_TOOLS`     | Backend  | Enables `/admin/*` endpoints                               |
| `FRONTEND_ORIGIN`        | Backend  | CORS allowlist override                                    |
| `OPENAI_API_KEY`         | Backend  | LlamaIndex embedding model (e.g. `text-embedding-3-large`) |
| `GOOGLE_CREDS_JSON`      | Backend  | Service account credentials (Base64-encoded)               |
| `GOOGLE_TOKEN_JSON`      | Backend  | Optional OAuth token (Base64-encoded)                      |
| `GOOGLE_CLIENT_ID`       | Both     | Google OAuth client ID                                     |
| `GOOGLE_CLIENT_SECRET`   | Backend  | Google OAuth client secret                                 |
| `OAUTH_REDIRECT_URI`     | Both     | Redirect URI after login                                   |
| `POST_AUTH_REDIRECT_URI` | Backend  | Redirect URI post-auth                                     |
| `INDEX_ROOT`             | Backend  | Filesystem path for semantic index                         |
| `KB_EMBED_MODEL`         | Backend  | Embedding model for KB                                     |
| `RELAY_PROJECT_ROOT`     | Backend  | Local path base                                            |
| `NEXT_PUBLIC_API_KEY`    | Frontend | API key exposed to the browser                             |
| `NEXT_PUBLIC_API_URL`    | Frontend | Backend root for all API calls                             |
| `NEXT_PUBLIC_RELAY_KEY`  | Frontend | Optional: UI config or dev-only usage                      |

---

## 🧪 Google Docs Sync

Relay syncs Google Docs → Markdown into `/docs/imported`.

### Required Variables

| Variable            | Purpose                                          |
| ------------------- | ------------------------------------------------ |
| `GOOGLE_CREDS_JSON` | Base64-encoded client-secret JSON                |
| `GOOGLE_TOKEN_JSON` | (Optional) Base64-encoded OAuth token JSON       |
| `ENV`               | Must be `local` for OAuth to launch browser flow |

### OAuth Flow

1. Visit: `http://localhost:8000/google/auth`
2. Login → redirect to `/google/callback`
3. Token saved to `frontend/sync/token.json`

Or run manually:

```bash
python scripts/authorize_google.py
```

---

## 🌐 CORS & Frontend Access

Relay uses FastAPI’s `CORSMiddleware`. Environments behave as follows:

| ENV                  | Allowed Origins                       | Notes                         |
| -------------------- | ------------------------------------- | ----------------------------- |
| `local`              | `localhost`, `relay.wildfireranch.us` | Uses `FRONTEND_ORIGIN` if set |
| `preview`, `staging` | `*` (wildcard)                        | For dev/testing only          |
| `main`               | `FRONTEND_ORIGIN` enforced            | Lock down for prod            |

✅ Custom headers `X-API-Key` and `X-User-Id` are explicitly allowed.
⚠️ Ensure `OPTIONS` is allowed by your hosting provider (e.g., Railway Edge Rules).

### Smoke Test

```bash
curl -X OPTIONS https://relay.wildfireranch.us/kb/search \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: X-API-Key" -I
```

Expect:

```
HTTP/2 200
Access-Control-Allow-Origin: *
Access-Control-Allow-Headers: X-API-Key, Content-Type
Access-Control-Allow-Methods: GET, POST, OPTIONS
```

---

## 🔎 Key Endpoints

| Path                      | Description                      | Auth Required            |
| ------------------------- | -------------------------------- | ------------------------ |
| `/ask`                    | GPT Q\&A with context            | ✅                        |
| `/kb/search`              | Semantic search                  | ✅                        |
| `/docs/sync`              | Google Docs → Markdown sync      | ✅                        |
| `/control/queue_action`   | Queue agent suggestion           | ✅                        |
| `/control/approve_action` | Approve queued action            | ✅                        |
| `/admin/reindex`          | Manual rebuild of semantic index | ✅ (`ENABLE_ADMIN_TOOLS`) |

---

## 🧰 Local Dev

### Backend

```bash
uvicorn main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

---

## 🗂 Related Docs

* [`/docs/PROJECT_SUMMARY.md`](./docs/PROJECT_SUMMARY.md)
* [`/docs/RELAY_CODE_UPDATE.md`](./docs/RELAY_CODE_UPDATE.md)
* [`.env.example`](./.env.example)

---

*Last updated: 2025-06-19*
