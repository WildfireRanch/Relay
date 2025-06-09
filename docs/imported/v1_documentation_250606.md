1. Functionality
Conversational AI Agent (/ask): Leverages GPT‑4o to handle free‑form queries, cite sources, and suggest code patches based on context.
Semantic Knowledge Base (/kb/search): Performs vector similarity searches over imported Markdown docs (Google‑synced or generated) using SQLite + LangChain embeddings.
Google Docs Sync (/docs/sync): OAuth2‑powered flow that imports designated Drive documents into docs/imported, converting them to Markdown and refreshing the KB.
Documentation Browser (/docs/list, /docs/view): Lists available docs and serves their content for in‑app viewing.
Action Queue & Patch Approval (/control/queue\_action, /control/approve\_action): Stages file writes or code modifications for developer review before applying changes.
Environment Validator (/check/env\_keys): Validates required environment variables at startup, preventing misconfigurations.
Dashboard UI: Next.js/React interface with panels:
AskAgent – Chat interface for AI queries
SearchPanel – KB lookup by keyword
DocsViewer – Two‑pane Markdown viewer with sync trigger
ActionQueuePanel – Pending patches list and one‑click approval
2. How to Use
Prerequisites: Node.js, Python 3.12+, uvicorn, npm, and valid Google OAuth credentials.
Environment Setupcp .env.example .env
# Populate with:
# OPENAI\_API\_KEY, API\_KEY, GOOGLE\_CREDS\_JSON, (optional) GOOGLE\_TOKEN\_JSON
Install & Launch Services# Backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
# Frontend
cd frontend
npm install
npm run dev # runs on port 3000
Sync Documentation
In browser, go to http://localhost:8080/docs/sync
Authenticate via Google (first run)
Confirm import: Markdown files appear under docs/imported.
Interact
AskAgent: Ask questions in Dashboard, view citations and suggestions.
SearchPanel: Search KB for context or troubleshooting docs.
DocsViewer: Navigate synced docs; click “Sync” to refresh.
ActionQueuePanel: Review queued patches, click “Approve” to apply.
Direct API CallsGET /ask?query=Your+question
POST /api/kb/search { query: string, k: number }
POST /control/queue\_action { patch details }
POST /control/approve\_action { action\_id }
POST /docs/sync
GET /docs/list
GET /docs/view?path=imported/YourDoc.md
3. Technical Details
Project Structure
/ # Root
├─ main.py # FastAPI startup & route registration
├─ routes/
│ ├─ ask.py # /ask endpoint logic
│ ├─ control.py # queue\_action, approve\_action
│ ├─ docs.py # sync, list, view routes
│ └─ check.py # /check/env\_keys
├─ services/
│ ├─ agent.py # GPT prompt composition & context loader
│ ├─ kb.py # embedding & search utils
│ ├─ google\_docs\_sync.py # OAuth flow & Drive MD conversion
│ └─ settings.py # Env var schema & loader
├─ docs/
│ ├─ imported/ # Google‑sync Markdown files
│ └─ generated/ # AI‑generated summaries
├─ data/
│ └─ pending\_actions.json # Queued patch state
├─ logs/
│ └─ actions.log # Patch application history
├─ frontend/
│ ├─ src/app/page.tsx # Main Dashboard layout
│ ├─ components/
│ │ ├─ AskAgent.tsx
│ │ ├─ SearchPanel.tsx
│ │ ├─ DocsViewer.tsx
│ │ └─ ActionQueuePanel.tsx
│ └─ api/ # Next.js API proxy (optional)
└─ tests/ # Unit/integration test stubs
Key Code Highlights
SYSTEM\_PROMPT in services/agent.py: Central AI persona & context roles.
Context Loaders: agent.read\_source\_files() reads code snippets; agent.read\_docs() pulls Markdown docs.
Embeddings: kb.embed\_doc() & kb.search() use OpenAI's embedding model, cache in SQLite DB.
OAuth2 Flow: google\_docs\_sync.py uses InstalledAppFlow for local webserver auth, token persistence.
Patch Workflow: data/pending\_actions.json stores staged patch diffs; control.py applies approved diffs to disk.
4. Actual Routes & Descriptions
These endpoints are loaded from current code:
GET / — Sanity check (uptime, load balancer) (main.py)
GET /ask — AI query interface (routes/ask.py)
GET /check/env\_keys — Env var validation (routes/check.py)
POST /docs/sync — Trigger Google Docs import (routes/docs.py)
GET /docs/list — List available docs (routes/docs.py)
GET /docs/view — Serve markdown content (routes/docs.py)
POST /control/queue\_action — Stage file/patch write (routes/control.py)
POST /control/approve\_action — Approve and apply staged action (routes/control.py)
POST /api/kb/search — Semantic search payload (routes/kb.py)
5. Impact & Metrics (Placeholders)
Google Docs Imported: \_\_ docs
Markdown Files: \_\_ files in docs/imported
API Hits: /ask \_\_ calls, KB search \_\_ calls
Patches Queued/Applied: \_\_ / \_\_
Avg. Latency: /ask \_\_ ms, /api/kb/search \_\_ ms
Onboarding Time: Setup from zero to running in \_\_ minutes
Fill in with real telemetry to quantify v1 success.
End of Release Notes & Documentation for v1.
V1 Relay Command Center – Release Notes & Documentation
1. Functionality
Conversational AI Agent (/ask): Leverages GPT‑4o to handle free‑form queries, cite sources, and suggest code patches based on context.
Semantic Knowledge Base (/kb/search): Performs vector similarity searches over imported Markdown docs (Google‑synced or generated) using SQLite + LangChain embeddings.
Google Docs Sync (/docs/sync): OAuth2‑powered flow that imports designated Drive documents into docs/imported, converting them to Markdown and refreshing the KB.
Documentation Browser (/docs/list, /docs/view): Lists available docs and serves their content for in‑app viewing.
Action Queue & Patch Approval (/control/queue\_action, /control/approve\_action): Stages file writes or code modifications for developer review before applying changes.
Environment Validator (/check/env\_keys): Validates required environment variables at startup, preventing misconfigurations.
Dashboard UI: Next.js/React interface with panels:
AskAgent – Chat interface for AI queries
SearchPanel – KB lookup by keyword
DocsViewer – Two‑pane Markdown viewer with sync trigger
ActionQueuePanel – Pending patches list and one‑click approval
2. How to Use
Prerequisites: Node.js, Python 3.12+, uvicorn, npm, and valid Google OAuth credentials.
Environment Setup
cp .env.example .env
# Populate with:
# OPENAI\_API\_KEY, API\_KEY, GOOGLE\_CREDS\_JSON, (optional) GOOGLE\_TOKEN\_JSON
Install & Launch Services
# Backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
# Frontend
cd frontend
npm install
npm run dev # runs on port 3000
Sync Documentation
In browser, go to http://localhost:8080/docs/sync
Authenticate via Google (first run)
Confirm import: Markdown files appear under docs/imported.
Interact
AskAgent: Ask questions in Dashboard, view citations and suggestions.
SearchPanel: Search KB for context or troubleshooting docs.
DocsViewer: Navigate synced docs; click “Sync” to refresh.
ActionQueuePanel: Review queued patches, click “Approve” to apply.
Direct API Calls
GET /ask?query=Your+question
POST /api/kb/search { query: string, k: number }
POST /control/queue\_action { patch details }
POST /control/approve\_action { action\_id }
POST /docs/sync
GET /docs/list
GET /docs/view?path=imported/YourDoc.md
3. Technical Details
Project Structure
/ # Root
├─ main.py # FastAPI startup & route registration
├─ routes/
│ ├─ ask.py # /ask endpoint logic
│ ├─ control.py # queue\_action, approve\_action
│ ├─ docs.py # sync, list, view routes
│ └─ check.py # /check/env\_keys
├─ services/
│ ├─ agent.py # GPT prompt composition & context loader
│ ├─ kb.py # embedding & search utils
│ ├─ google\_docs\_sync.py # OAuth flow & Drive MD conversion
│ └─ settings.py # Env var schema & loader
├─ docs/
│ ├─ imported/ # Google‑sync Markdown files
│ └─ generated/ # AI‑generated summaries
├─ data/
│ └─ pending\_actions.json # Queued patch state
├─ logs/
│ └─ actions.log # Patch application history
├─ frontend/
│ ├─ src/app/page.tsx # Main Dashboard layout
│ ├─ components/
│ │ ├─ AskAgent.tsx
│ │ ├─ SearchPanel.tsx
│ │ ├─ DocsViewer.tsx
│ │ └─ ActionQueuePanel.tsx
│ └─ api/ # Next.js API proxy (optional)
└─ tests/ # Unit/integration test stubs
Key Code Highlights
SYSTEM\_PROMPT in services/agent.py: Central AI persona & context roles.
Context Loaders: agent.read\_source\_files() reads code snippets; agent.read\_docs() pulls Markdown docs.
Embeddings: kb.embed\_doc() & kb.search() use OpenAI's embedding model, cache in SQLite DB.
OAuth2 Flow: google\_docs\_sync.py uses InstalledAppFlow for local webserver auth, token persistence.
Patch Workflow: data/pending\_actions.json stores staged patch diffs; control.py applies approved diffs to disk.
4. Actual Routes & Descriptions
These endpoints are loaded from current code:
GET / — Sanity check (uptime, load balancer) (main.py)
GET /ask — AI query interface (routes/ask.py)
GET /check/env\_keys — Env var validation (routes/check.py)
POST /docs/sync — Trigger Google Docs import (routes/docs.py)
GET /docs/list — List available docs (routes/docs.py)
GET /docs/view — Serve markdown content (routes/docs.py)
POST /control/queue\_action — Stage file/patch write (routes/control.py)
POST /control/approve\_action — Approve and apply staged action (routes/control.py)
POST /api/kb/search — Semantic search payload (routes/kb.py)
5. Impact & Metrics (Placeholders)
Google Docs Imported: \_\_ docs
Markdown Files: \_\_ files in docs/imported
API Hits: /ask \_\_ calls, KB search \_\_ calls
Patches Queued/Applied: \_\_ / \_\_
Avg. Latency: /ask \_\_ ms, /api/kb/search \_\_ ms
Onboarding Time: Setup from zero to running in \_\_ minutes
Fill in with real telemetry to quantify v1 success.
End of Release Notes & Documentation for v1.