to newcomer
Jun 6
WildfireRanch/Relay
Archive
Share
Explain the codebase to a newcomer. What is the general structure, what are the important things to know, and what are some pointers for things to learn next?
Copy
Repository Overview
This project hosts “Relay,” a small FastAPI backend with a Next.js/React frontend. The repository structure is straightforward:
/main.py – FastAPI application entry
/routes/ – REST endpoints
/services/ – Core backend logic
/frontend/ – Next.js frontend
/docs/ – Generated/Imported docs
/data/ & /logs/ – Action queue and logging files
/tests/ – (mostly empty) test placeholders
Backend
main.py initializes FastAPI, loads environment variables, configures CORS and mounts the route modules:
9 from dotenv import load\_dotenv
10 load\_dotenv()
...
35 app.add\_middleware(
...
49 app.include\_router(ask.router)
50 app.include\_router(status.router)
51 app.include\_router(control.router)
52 app.include\_router(docs.router)
53 app.include\_router(oauth.router)
Services
services/agent.py
Implements the OpenAI-powered assistant. It determines if code/doc context is needed, can auto-generate docs, and queues new files through /control/queue\_action.
Key logic includes the system prompt and context gathering helpers:
15 SYSTEM\_PROMPT = """
You are Relay...
...
30 def needs\_code\_context(query: str) -> bool:
...
41 async def answer(query: str) -> str:
...
85 async def generate\_doc\_for\_path(rel\_path: str) -> str:
...
136 def read\_source\_files(roots=["services"], exts=[".py", ".tsx", ".ts"]):
...
166 def read\_docs(root="docs", exts=[".md", ".txt"]):
services/google\_docs\_sync.py
Handles Google OAuth, downloads docs from a specified Drive folder, converts them to Markdown, and saves them under docs/imported:
1 # File: services/google\_docs\_sync.py
...
31 def get\_google\_service():
...
138 def sync\_google\_docs() -> list:
...
152 if enabled:
153 sync\_google\_docs()
services/kb.py
Embeds markdown docs into a SQLite-based vector database using LangChain to enable semantic search:
11 DOCS\_DIR = ROOT / "docs"
...
35 def embed\_docs():
...
53 def cosine\_similarity(v1, v2):
...
58 def search(query, k=4):
Other helpers include logging (services/logs.py) and environment validation (services/settings.py).
Routes
FastAPI endpoints live in routes/. Examples:
routes/ask.py – exposes /ask for user questions and /test\_openai for verifying OpenAI access.
routes/control.py – provides endpoints for writing files, queuing actions, approving queued actions, and retrieving logs:
14 def auth(key: str = Header(..., alias="X-API-Key")):
...
45 @router.post("/write\_file")
...
69 @router.post("/queue\_action")
...
94 @router.post("/approve\_action")
...
134 @router.get("/list\_log")
routes/docs.py – manages document syncing and knowledge-base refreshing:
31 @router.post("/update\_context")
...
58 @router.post("/sync\_google")
63 @router.post("/sync")
74 @router.post("/refresh\_kb")
85 @router.post("/full\_sync")
98 @router.get("/list")
109 @router.get("/view")
Frontend
The frontend/ folder contains a Next.js app. The home page (src/app/page.tsx) links to Docs, Control, and Status pages and embeds several React components:
3 import AskAgent from "@/components/AskAgent/AskAgent"
...
10 
...
23 
...
29 
33 
Key components include:
AskAgent – simple form that queries /ask.
ActionQueuePanel – lists and approves queued actions by hitting /control/\* endpoints.
DocsViewer – displays Markdown files and allows manual Google Docs sync.
SearchPanel – calls the /kb/search API.
The frontend also has minimal API routes under src/app/api/ that forward requests to the backend, allowing the Next.js app to act as a thin UI over the FastAPI service.
Data and Logging
Queued actions are stored in data/pending\_actions.json, and executed actions are logged to logs/actions.log. Basic session logs are written via services/logs.py. The docs directory (docs/) contains imported or generated documentation used by the knowledge base.
Getting Started / Next Steps
Environment Setup – ensure .env contains OPENAI\_API\_KEY, GOOGLE\_CREDS\_JSON, optional GOOGLE\_TOKEN\_JSON, and API\_KEY. main.py loads these via dotenv on startup.
Running Locally – start the backend (python main.py or uvicorn main:app) and the frontend (npm run dev within frontend/).
Docs Sync and KB – explore services/google\_docs\_sync.py and the /docs routes to understand how Google Docs are pulled and embedded.
Agent Logic – services/agent.py is central to how the assistant gathers context and answers questions; studying its helper functions is useful for extending functionality.
Testing – the tests/ directory contains placeholders. Adding real tests (for routes, sync logic, etc.) would be a logical area for improvement.
Overall, the project integrates OpenAI, Google Drive, and a simple knowledge base to provide a conversational assistant with access to synced documentation and the ability to queue file changes. The Next.js frontend offers a small dashboard for user interaction. Future work might include fleshing out tests, expanding route functionality, or enhancing the frontend.
can you put this in a pasteable document
Copy
Below is a pasteable Markdown document summarizing the repository structure, components, and suggested next steps:
Relay Repository Overview
This project contains a small FastAPI backend paired with a Next.js/React frontend. The layout is straightforward:
/main.py – FastAPI application entry point
/routes/ – REST API endpoints
/services/ – Core backend logic
/frontend/ – Next.js frontend
/docs/ – Generated/imported documentation
/data/ & /logs/ – Queued actions and logs
/tests/ – Mostly empty placeholders
Backend
main.py initializes FastAPI, loads environment variables, configures CORS, and registers route modules.
Key Service Modules
services/agent.py – Implements the OpenAI‑powered assistant. Handles context gathering, question answering, and documentation generation.
services/google\_docs\_sync.py – Syncs documentation from a Google Drive folder and stores Markdown files under docs/imported.
services/kb.py – Embeds Markdown docs into a SQLite vector database for semantic search.
Other helper modules manage logging and environment validation.
Routes
routes/ask.py – /ask endpoint and an OpenAI test route.
routes/control.py – Endpoints for writing files, queuing/approving actions, and retrieving logs.
routes/docs.py – Manages document syncing and knowledge-base refreshing.
Frontend
Located in frontend/, the Next.js app serves a dashboard with components to interact with the backend:
AskAgent – Form for querying /ask.
ActionQueuePanel – Approve queued actions via /control/\*.
DocsViewer – Display Markdown docs and sync with Google Docs.
SearchPanel – Query the knowledge base.
Data and Logging
data/pending\_actions.json – Stores queued actions.
logs/actions.log – Logs executed actions.
docs/ – Contains imported/generated docs used by the knowledge base.
Getting Started
Environment Variables – Ensure .env includes OPENAI\_API\_KEY, GOOGLE\_CREDS\_JSON, optional GOOGLE\_TOKEN\_JSON, and API\_KEY.
Run Locally – Start the backend (python main.py or uvicorn main:app) and the frontend (npm run dev inside frontend/).
Docs & KB – Study services/google\_docs\_sync.py and the /docs routes to see how documentation is synced and indexed.
Agent Logic – Review services/agent.py to understand how context is gathered and responses are generated.
Testing – The tests/ directory is mostly empty. Adding real tests for routes and sync logic is a natural improvement.
This text can be copied directly into any document or note-taking tool.