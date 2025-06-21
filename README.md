# 🤠 Relay Command Center – Readme

> Cloud-native, agent-powered AI control system with semantic doc search, human-in-the-loop patching, contextual code awareness, and Google Docs sync.

---

## 🚀 Features

* GPT-4o-powered agent with patch suggestions and approval
* Semantic search using LlamaIndex + OpenAI embeddings
* Modular frontend (Next.js) and backend (FastAPI)
* Google Docs → Markdown sync with OAuth 2.0
* Secure, secretless deployment via Railway and Vercel
* CORS-aware, audit-logged API with per-env controls
* Context-aware agent prompt injection with domain/topic overlays
* `/status/code` for source tracking + freshness
* Auto-generated `/docs/generated/relay_code_map.md`

---

## 👭 System Architecture

```
[ Next.js SPA (Vercel) ]
        ⇅ SSO + API
[ FastAPI Backend (Railway) ]
        ⇅ REST API
[ Semantic Index (LlamaIndex + OpenAI) ]
        ⇅
[ Markdown Docs (/docs/imported, /context/) ]
```

* Frontend: `frontend/`
* Backend: `main.py`, `routes/`, `services/`
* Docs: `/docs/imported/`, `/docs/generated/`, `/context/`
* Index: `data/index/<env>/<model>/`
* Audit Log: `logs/audit.jsonl`

---

## 🔐 Environment Variables (Quick Reference)

For full details, see [`/docs/PROJECT_SUMMARY.md`](./docs/PROJECT_SUMMARY.md)

| Variable                 | Scope    | Purpose                                                    |
| ------------------------|----------|------------------------------------------------------------|
| `ENV`                   | Backend  | `local`, `develop`, `main` for env-specific logic          |
| `API_KEY`               | Backend  | Master API key for protected endpoints                     |
| `ENABLE_ADMIN_TOOLS`   | Backend  | Enables `/admin/*` endpoints                               |
| `FRONTEND_ORIGIN`      | Backend  | CORS allowlist override                                    |
| `OPENAI_API_KEY`       | Backend  | LlamaIndex embedding model (e.g. `text-embedding-3-large`) |
| `GOOGLE_CREDS_JSON`    | Backend  | Service account credentials (Base64-encoded)               |
| `GOOGLE_TOKEN_JSON`    | Backend  | Optional OAuth token (Base64-encoded)                      |
| `GOOGLE_CLIENT_ID`     | Both     | Google OAuth client ID                                     |
| `GOOGLE_CLIENT_SECRET` | Backend  | Google OAuth client secret                                 |
| `OAUTH_REDIRECT_URI`   | Both     | Redirect URI after login                                   |
| `POST_AUTH_REDIRECT_URI`| Backend | Redirect URI post-auth                                     |
| `INDEX_ROOT`           | Backend  | Filesystem path for semantic index                         |
| `KB_EMBED_MODEL`       | Backend  | Embedding model for KB                                     |
| `RELAY_PROJECT_ROOT`   | Backend  | Local path base                                            |
| `NEXT_PUBLIC_API_KEY`  | Frontend | API key exposed to the browser                             |
| `NEXT_PUBLIC_API_URL`  | Frontend | Backend root for all API calls                             |
| `NEXT_PUBLIC_RELAY_KEY`| Frontend | Optional: UI config or dev-only usage                      |

---

## 🧠 Context Intelligence

Relay supports hybrid awareness through both code and operational context:

- Loads `/docs/generated/global_context.md` or `.auto.md`
- Pulls `context-*` Google Docs → `/context/*.md`
- Injects code, semantic results, and project docs per topic into prompts
- Rebuilds `global_context.auto.md` daily from `/context/*.md`
- `/status/context` for freshness + file inventory
- `/status/code` to view tracked source files, timestamps, and active functions

To trigger context sync:
```bash
curl -X POST $RELAY_URL/admin/sync_context_docs
```

---

## 🔁 Using Echo (Agent)

```bash
POST /ask
{
  "query": "How is the miner throttled when solar is low?",
  "files": ["services/miner_control.py"],
  "topics": ["mining", "solarshack"]
}
```

Echo auto-injects:
- Project summary
- Semantic recall
- Domain context (e.g. `context-solarshack`)
- Function names from specified files

---

## 🔎 Key Endpoints

| Path                           | Description                              | Auth Required            |
|--------------------------------|------------------------------------------|--------------------------|
| `/ask`                         | GPT Q&A with code+context                | ✅                        |
| `/kb/search`                   | Semantic search                          | ✅                        |
| `/docs/sync`                   | Google Docs → Markdown sync              | ✅                        |
| `/admin/reindex`               | Manual rebuild of semantic index         | ✅                        |
| `/admin/generate_auto_context`| Regenerate auto global context           | ✅                        |
| `/admin/sync_context_docs`     | Pull `context-*` docs from Google        | ✅                        |
| `/status/context`              | View current context state               | ❌ Public                 |
| `/status/code`                 | Source file awareness + freshness check  | ❌ Public                 |

---

## 📚 Documentation Outputs

| File                                      | Purpose                                       |
|-------------------------------------------|-----------------------------------------------|
| `/docs/generated/global_context.md`       | Manually curated global context               |
| `/docs/generated/global_context.auto.md`  | Auto-generated from `/context/*.md`           |
| `/docs/generated/relay_code_map.md`       | Live file + function snapshot from source     |

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

*Last updated: 2025-06-20*
