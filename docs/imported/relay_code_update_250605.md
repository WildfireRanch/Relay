✅ Relay Project Summary – Updated (As of Today)
🚀 Frontend (Next.js + React)
page.tsx
✅ GET /api/docs/list → returns `{ "files": [...] }`
🔁 /docs/sync\_google is deprecated — replaced by `/docs/sync` (returns `{ "synced_docs": [...] }`)
AskAgent.tsx
✅ Sends GET requests to /ask (CORS-safe, no preflight)
✅ Displays GPT-4o output with loading state
✅ Stripped headers to eliminate CORS preflight errors
✅ Uses process.env.NEXT\_PUBLIC\_RELAY\_KEY for dev logs only
SearchPanel.tsx
✅ POST /api/kb/search
✅ Displays top-k semantic matches from FastAPI:
Title
Snippet
Similarity score
✅ Type-safe with KBResult
✅ Includes enter key trigger and loading spinner
DocsViewer.tsx
✅ GET /api/docs/list
✅ GET /api/docs/view?path=...
✅ Two-panel native layout (left = file list, right = scrollable viewer)
✅ Pulls from /docs/imported/ and /docs/generated/
🧠 Backend (FastAPI + LangChain)
Core Routes
🔁 /docs/sync\_google is deprecated — replaced by /docs/sync with better logging
📁 Backend Modules
services/kb.py
✅ Embeds docs using text-embedding-3-small
✅ SQLite stores: path, chunks, cosine sim metadata
✅ KB result scoring used in /api/kb/search
services/settings.py
✅ .env loaded early via load\_dotenv()
✅ assert\_env() enforces critical keys (OPENAI\_API\_KEY, etc.)
services/google\_docs\_sync.py
✅ Uses run\_console() for CLI OAuth
✅ Pulls .gdoc from Command\_Center/
✅ Converts to Markdown, saved to /docs/imported/\*.md
⚠️ Requires token.json (manual upload to Railway)
services/agent.py
✅ Handles GPT query routing, context building
✅ read\_source\_files() now honors RELAY\_PROJECT\_ROOT ✅
✅ Logs missing folders, loads code/doc context dynamically
✅ Queues patch suggestions via /control/queue\_action
✅ GPT answers: human-like, citation-aware, can trigger actions
🧠 AI Integration
✅ GPT-4o for natural language responses, summaries, patch generation
✅ LangChain + OpenAI embeddings for search
✅ .env includes:
OPENAI\_API\_KEY
API\_KEY
RELAY\_PROJECT\_ROOT=/app ✅
🧩 Project Infrastructure & Reliability
✅ FastAPI runs on port 8080
✅ CORS fully configured (wildfire + localhost + vercel) ✅
✅ /ask OPTIONS issue solved (wildcard + no custom headers) ✅
✅ All doc folders created at boot (/docs/imported, /docs/generated)
✅ Canvas patch system live (tracked in Vercel + Railway)
✅ .env.example documents required keys
✅ API keys now redacted in logs
🔧 Remaining TODOs
Add same env-root logic to read\_docs() function
Reinstate X-API-Key support securely (via Vercel backend proxy or signed tokens)
Enable patch approval UI in control panel
Optionally add /status/version route for deploy traceability
Let me know if you’d like this saved to /docs/generated/relay\_status.md or queued to /control/queue\_action.