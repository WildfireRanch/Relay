✅ Relay Project Summary – Status as of Commit
🚀 Frontend (Next.js + React)
page.tsx
Serves as the homepage
Includes:
AskAgent – GPT-powered interaction module
SearchPanel – semantic search into synced docs
Link to /docs route with DocsViewer
SearchPanel.tsx
POSTs to /api/kb/search
Displays top-k semantic matches with:
title
snippet
similarity score
DocsViewer.tsx
Fetches file list from /api/docs/list
Loads content from /api/docs/view?path=...
Clean 2-panel layout for viewing Markdown files
Scrollable, responsive, and client-friendly
🧠 Backend (FastAPI + LangChain)
Core Routes
/kb/search
Accepts { query: string, k: int }
Returns top-k cosine similarity matches from kb.sqlite3
/docs/list, /docs/view
Lists and returns content of .md or .txt files in /docs
/docs/sync\_google
Triggers sync from Google Drive → Markdown files under /docs/imported
/check/env\_keys
Scans services/ for os.getenv(...) calls
Verifies existence in .env
Flags missing, unused, or stale keys
📁 Backend Modules
services/kb.py
Embeds .md docs using OpenAIEmbeddings
Stores chunks + vectors + metadata in SQLite
Uses cosine similarity to power semantic search
Stores title, last\_updated, and embedding for each chunk
services/settings.py
Centralized config loader
Calls load\_dotenv() at startup
Provides assert\_env(...) for safe env enforcement
services/google\_docs\_sync.py
Auths with Google via OAuth
Locates your Command\_Center folder
Pulls .gdoc content → Markdown
Saves to docs/imported/\*.md
Rebuilt from scratch after Codespace reset
🧠 AI Readiness
LangChain + OpenAI fully integrated
text-embedding-3-small model powering embeddings
GPT-4o agent available via /ask route
Modular structure ready for more agents or chain workflows
🧩 Final Touches Before Commit
All code saved and updated
Fixed missing file (google\_docs\_sync.py)
Fully documented .env structure and validation
React panels: Search + DocsViewer operational