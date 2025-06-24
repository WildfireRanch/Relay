# 🤠 Relay Command Center – Readme

> Cloud-native, agent-powered AI control system with semantic doc/code search, human-in-the-loop patching, deep contextual code awareness, and Google Docs sync.

---

## 🚀 Features

* GPT-4o-powered agent with patch suggestions and human-in-the-loop approval
* Hybrid semantic search (LlamaIndex + OpenAI embeddings) over code/docs/context
* Modular Next.js frontend & FastAPI backend
* Google Docs → Markdown sync (OAuth 2.0, `/docs/imported` or `/context/`)
* Secure, secretless deployment (Railway, Vercel)
* CORS-aware, audit-logged API with per-env controls
* Context-aware prompt injection with topic overlays, code + docs + project context
* `/status/context` for live context file inventory + freshness
* `/status/code` for tracked source code, timestamp, and function mapping
* Deep session memory logs and robust action queue for patch suggestions

---

## 👭 System Architecture

```
[ Next.js SPA (Vercel) ]
        ⇅ Auth + API
[ FastAPI Backend (Railway) ]
        ⇅ REST API
[ Semantic Index (LlamaIndex + OpenAI) ]
        ⇅
[ Markdown Docs (/docs/imported, /context/, /docs/generated) ]
        ⇅
[ Action Queue, Session Memory, Audit Log ]
```

* **Frontend:** `frontend/`
* **Backend:** `main.py`, `routes/`, `services/`
* **Docs/Context:** `/docs/imported/`, `/docs/generated/`, `/context/`
* **Index:** `data/index/<env>/<model>/`
* **Session Memory:** `/logs/sessions/<user>.jsonl`
* **Audit Log:** `/logs/audit.jsonl`

---

## 🔐 Environment Variables (Quick Reference)

For details, see [`/docs/PROJECT_SUMMARY.md`](./docs/PROJECT_SUMMARY.md)

| Variable                 | Scope    | Purpose                                           |
| ------------------------ | -------- | ------------------------------------------------- |
| `ENV`                    | Backend  | `local`, `develop`, `main` for env-specific logic |
| `API_KEY`                | Backend  | Master API key for protected endpoints            |
| `ENABLE_ADMIN_TOOLS`     | Backend  | Enables `/admin/*` endpoints                      |
| `ENABLE_REFLECT_AND_PLAN` | Backend  | Run reflection step before answering |
| `FRONTEND_ORIGIN`        | Backend  | CORS allowlist override                           |
| `OPENAI_API_KEY`         | Backend  | For embeddings and agent chat/completions         |
| `GOOGLE_CREDS_JSON`      | Backend  | Service account credentials (Base64-encoded)      |
| `GOOGLE_TOKEN_JSON`      | Backend  | Optional OAuth token (Base64-encoded)             |
| `GOOGLE_CLIENT_ID`       | Both     | Google OAuth client ID                            |
| `GOOGLE_CLIENT_SECRET`   | Backend  | Google OAuth client secret                        |
| `OAUTH_REDIRECT_URI`     | Both     | Redirect URI after login                          |
| `POST_AUTH_REDIRECT_URI` | Backend  | Redirect URI post-auth                            |
| `INDEX_ROOT`             | Backend  | Filesystem path for semantic index                |
| `KB_EMBED_MODEL`         | Backend  | Embedding model for KB                            |
| `RELAY_PROJECT_ROOT`     | Backend  | Root path for doc/code/context scans              |
| `NEXT_PUBLIC_API_KEY`    | Frontend | API key exposed to browser                        |
| `NEXT_PUBLIC_API_URL`    | Frontend | Backend root for all API calls                    |

---

## 🧠 Context & Memory Intelligence

Relay supports hybrid context/memory awareness across docs, code, and operational files:

* Loads `/docs/generated/global_context.md` or `.auto.md`
* Pulls `context-*` Google Docs into `/context/*.md` and/or `/docs/imported`
* Injects code, semantic search results, project summaries, and per-topic docs into agent prompts
* Rebuilds `global_context.auto.md` daily from `/context/*.md`
* `/status/context` returns freshness and full file inventory (used in StatusPanel)
* `/status/code` returns tracked source files, last-modified timestamps, and mapped functions
* Deep logging of every `/ask` event: tracks context files used, prompt/response size, global context, fallback flag

**Note:** Place Markdown files in `/context/` or create `docs/generated/global_context.md` so `/status/context` has something to show.

**To trigger context/doc sync:**

```bash
curl -X POST $RELAY_URL/context/sync_docs
```

---

## 🔁 Using Echo (Agent)

### Agent Q\&A Example:

```bash
POST /ask
{
  "question": "How is the miner throttled when solar is low?",
  "files": ["services/miner_control.py"],
  "topics": ["mining", "solarshack"]
}
```

Echo will auto-inject:

* Project summary
* Semantic recall (via KB)
* Domain/project context (e.g. from `/context/context-solarshack.md`)
* Function names from specified files
* Global project context if present

To run the optional reflection & planning step, set `ENABLE_REFLECT_AND_PLAN=1` or
append `?reflect=1` to `/ask` requests.

---

## 🔎 Key Endpoints

| Path                           | Description                                    | Auth Required |
| ------------------------------ | ---------------------------------------------- | ------------- |
| `/ask`                         | GPT Q\&A with code+context                     | ✅             |
| `/kb/search`                   | Semantic search over code/docs/context         | ✅             |
| `/docs/sync`                   | Google Docs → Markdown/context sync            | ✅             |
| `/admin/reindex`               | Manual rebuild of semantic index               | ✅             |
| `/admin/generate_auto_context` | Regenerate auto global context from `/context` | ✅             |
| `/context/sync_docs`           | Pull all `context-*` docs from Google          | ✅             |
| `/control/queue_action`        | Queue agent patch/action                       | ✅             |
| `/control/approve_action`      | Approve queued action                          | ✅             |
| `/status/context`              | Current context state (public)                 | ❌             |
| `/status/code`                 | Source file/freshness status (public)          | ❌             |
| `/logs/sessions/all`           | All user memory logs (for MemoryPanel)         | ✅             |

---

## 🖥️ Web Dashboards

* **Control dashboard:** `/control` – view pending actions, execution logs, and the Memory Log panel.
* **Memory log viewer:** part of `/control` or fetch JSON via `/logs/sessions/all`.
* **Status page:** `/status` – shows context health and code inventory.

---

## 📚 Documentation Outputs

| File                                     | Purpose                                     |
| ---------------------------------------- | ------------------------------------------- |
| `/docs/generated/global_context.md`      | Manually curated global context             |
| `/docs/generated/global_context.auto.md` | Auto-generated from `/context/*.md`         |
| `/docs/generated/relay_code_map.md`      | Live file/function snapshot from source     |
| `/logs/sessions/<user>.jsonl`            | Session memory log per user                 |
| `/logs/audit.jsonl`                      | All patch/approval actions, fully auditable |

---

## 🧰 Local Dev

**Backend**

```bash
uvicorn main:app --reload
```

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

---

## 📝 How to extend

* **Add new context roots:** Update ContextEngine to scan new folders or cloud sources
* **Add new memory fields:** Edit `services/memory.py` and MemoryPanel.tsx as needed
* **Improve semantic search:** Tweak LlamaIndex indexing/split/embedding models
* **Automate sync:** Cron, webhook, or push-to-sync for Google Docs/Notion, etc.

---

*Last updated: 2025-06-23*
