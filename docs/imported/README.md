# Relay Command Center
FastAPI control plane for Wildfire Ranch agent workflows with a Next.js dashboard.

## Recent Changes (Ops, Cache, KB)
- Docs Ops (/docs/*)
  - Added a single, production‑grade `/docs/op_status` endpoint that never raises and reports both in‑flight async ops and lock files under `LOCK_DIR`. Duplicate/mis‑indented handlers were removed.
  - Long operations remain lock‑protected; use `/docs/op_status` to see `in_flight` and `locks` at a glance.
- Diagnostics
  - Fixed `/__router_diag` to be registered at module scope; it now reliably returns import diagnostics for `routes.docs`, `routes.kb`, and `routes.x_mirror`.
- Redis cache safety
  - `services/cache.py` no longer crashes on import. aioredis is imported lazily; `get_redis()` returns `None` if Redis is unavailable or `REDIS_URL` is unset.
  - New helpers: `key_for(*parts)` for simple namespacing and `keyed_hash(namespace, payload)` for stable hashed keys.
- Semantic Retriever (services/semantic_retriever.py)
  - Guarded KB adapter import; when unavailable, search degrades gracefully and logs a structured event.
  - Normalizes backend similarity to a consistent `score ∈ [0,1]` (cosine or inner‑product), and optionally applies a local `score_threshold`.
  - Public API explicitly declared via `__all__`; added `reindex_all(root)` with a stable, non‑throwing contract used by KB maintenance paths.
  - Safer env parsing for `SEMANTIC_DEFAULT_K`; additional docstrings and explicit typing for production clarity.

## Architecture Snapshot
- [main.py](./main.py) – App factory, CORS, core middleware, router mounting, health probes.
- [routes/](./routes) – Mounted APIs: ask, MCP, control queue, docs maintenance.
- [services/](./services) – Agent shims, knowledge-base/index tooling, Google Docs sync helpers.
- [frontend/src/app](./frontend/src/app) – Next.js routes actually shipped with the repo (`/`, `/ask`, `/docs`, `/control`, etc.).
- [docs/](./docs) – Markdown corpus consumed by the KB and docs routes.

## Route Matrix (Mounted)
| Endpoint | Method | Auth | Source | Notes |
| --- | --- | --- | --- | --- |
| `/Live` | GET | none | main.py:174 | Liveness probe returning `{"ok": true}`. |
| `/Ready` | GET | none | main.py:178 | Readiness probe; no dependency checks yet. |
| `/gh/debug/api-key` | GET | none | main.py:261 | Reports whether `OPENAI_API_KEY`/`GITHUB_APP_ID` are present. |
| `/ask` | OPTIONS | none | routes/ask.py:420 | Fixed 204 for CORS preflight. |
| `/ask` | POST | none | routes/ask.py:425 | Main MCP pipeline with retrieval gate and anti-parrot checks. |
| `/ask` | GET | none | routes/ask.py:730 | Legacy query param shim that dispatches to POST handler. |
| `/ask/stream` | POST | none | routes/ask.py:741 | Streams text via `agents.echo_agent.stream`; returns 501 if agent missing. |
| `/ask/codex_stream` | POST | none | routes/ask.py:782 | Streams code patches via `agents.codex_agent.stream`; returns 501 if agent missing. |
| `/mcp/ping` | GET | none | routes/mcp.py:207 | Lightweight status for MCP stack with safe-mode flag. |
| `/mcp/diag` | GET | none | routes/mcp.py:215 | Lists filesystem/import status for agents and retrievers. |
| `/mcp/diag_ctx` | GET | none | routes/mcp.py:268 | Builds context using tiered retrievers; returns errors inline. |
| `/mcp/run` | POST | none | routes/mcp.py:308 | Executes MCP agent; optional safe-mode fallback to echo when `MCP_SAFE_MODE` is true. |
| `/control/queue_action` | POST | `X-API-Key` (matches `API_KEY`) | routes/control.py:84 | Enqueues pending action in `data/pending_actions.json`. |
| `/control/list_queue` | GET | `X-API-Key` | routes/control.py:105 | Returns pending actions. |
| `/control/approve_action` | POST | `X-API-Key` | routes/control.py:113 | Executes action via agent dispatch or write-file fallback. |
| `/control/deny_action` | POST | `X-API-Key` | routes/control.py:185 | Marks action as denied and logs outcome. |
| `/control/list_log` | GET | `X-API-Key` | routes/control.py:219 | Streams JSONL history from `logs/actions.log`. |
| `/control/write_file` | POST | `X-API-Key` | routes/control.py:231 | Writes arbitrary file relative to repo root. |
| `/control/test` | POST | `X-API-Key` | routes/control.py:251 | Direct call into `control_agent.run` for manual execution. |
| `/docs/list` | GET | stub (no check) | routes/docs.py:71 | Enumerates markdown under `docs/imported` and `docs/generated`. |
| `/docs/view` | GET | stub | routes/docs.py:98 | Returns file content if path resolves inside `/docs`. |
| `/docs/sync` | POST | stub | routes/docs.py:111 | Runs Google Drive sync then `kb.api_reindex()` (currently missing) and cache clear. |
| `/docs/refresh_kb` | POST | stub | routes/docs.py:122 | Calls `kb.api_reindex()` only; fails while function is absent. |
| `/docs/full_sync` | POST | stub | routes/docs.py:131 | Combines `/docs/sync` + `/docs/refresh_kb`; inherits same failure. |
| `/docs/promote` | POST | stub | routes/docs.py:142 | Copies selected doc to canonical root and reindexes. |
| `/docs/prune_duplicates` | POST | stub | routes/docs.py:165 | Removes duplicate doc IDs then reindexes. |
| `/docs/mark_priority` | POST | stub | routes/docs.py:188 | Writes metadata block to doc and reindexes. |

## Optional/Disabled Routes
| Router | Status |
| --- | --- |
| `routes.status` | Commented out in `main.py:203`; not mounted. |
| `routes.index` | Commented out in `main.py:204`; not mounted. |
| `routes.integrations_github` | Commented out in `main.py:205`; not mounted. |
| `routes.kb` | Commented out in `main.py:206`; reindex/search endpoints unavailable. |
| `routes.search` | Commented out in `main.py:207`; no public KB search router. |
| `routes.embeddings` | Commented out in `main.py:208`; embeddings APIs disabled. |
| `routes.github_proxy` | Commented out in `main.py:209`; GitHub passthrough disabled. |
| `routes.oauth` | Commented out in `main.py:210`; OAuth flows offline. |
| `routes.debug` | Commented out in `main.py:211`; debug toolkit disabled. |
| `routes.codex` | Commented out in `main.py:212`; legacy codex APIs unavailable. |
| `routes.logs` | Commented out in `main.py:213`; log APIs disabled. |
| `routes.status_code` | Commented out in `main.py:214`; HTTP-code tester off. |
| `routes.webhooks_github` | Commented out in `main.py:215`; webhook receiver off. |
| `routes.admin` | Commented out in `main.py:216`; admin APIs disabled. |
| `routes.logs_sessions` | Commented out in `main.py:217`; memory log APIs disabled. |
| `routes.context` | Commented out in `main.py:218`; no `/context/*` routes. |

## Environment & Setup
| Name | Default / Required | Used by | Notes |
| --- | --- | --- | --- |
| `ENV` | default `dev` | services/config.py:7, services/google_docs_sync.py:83 | Selects index subdir and controls Google auth fallback. |
| `FRONTEND_ORIGINS` | optional | main.py:139 | Comma/space list of allowed origins; falls back to `https://status.wildfireranch.us`. |
| `FRONTEND_ORIGIN_REGEX` | default `^https://([a-z0-9-]+\.)?wildfireranch\.us$` | main.py:143 | Optional wildcard to allow subdomains. |
| `HTTP_TIMEOUT_S` | default `35` | main.py:171 | Request-level timeout enforced by middleware. |
| `API_KEY` | required for control routes | routes/control.py:42 | `X-API-Key` header must match for any `/control/*` call. |
| `ASK_MIN_MAX_SCORE` / `KB_SCORE_THRESHOLD` | default `0.35` | routes/ask.py:517 | Retrieval gate min similarity. |
| `ASK_MIN_HITS` / `KB_MIN_HITS` | default `1` | routes/ask.py:517 | Required KB hit count. |
| `ANTI_PARROT_MAX_CONTIGUOUS_MATCH` | default `180` | routes/ask.py:108 | Max copy length before anti-parrot trips. |
| `ANTI_PARROT_JACCARD` | default `0.35` | routes/ask.py:112 | Min novelty threshold. |
| `FINAL_TEXT_MAX_LEN` | default `20000` | routes/ask.py:116 | Clamp for final text length. |
| `ASK_TIMEOUT_S` | default `60` | routes/ask.py:120 | Timeout passed to downstream agents. |
| `MCP_SAFE_MODE` | default `false` | routes/mcp.py:199 | Enables echo fallback when MCP agent import fails. |
| `RERANK_MIN_SCORE_GLOBAL` / `SEMANTIC_SCORE_THRESHOLD` | optional | routes/mcp.py:279, services/kb.py:344 | Tightens retriever score filtering. |
| `KB_EMBED_MODEL` / `OPENAI_EMBED_MODEL` | default `text-embedding-3-large` | services/config.py:8 | Selects embedding model name. |
| `INDEX_ROOT` | default `./index/<ENV>` | services/config.py:15 | Root for persisted LlamaIndex storage. |
| `INDEX_DIR` | default `<INDEX_ROOT>/<MODEL>` | services/config.py:16 | Final index directory; created on import. |
| `RELAY_PROJECT_ROOT` | default repo root | services/kb.py:54 | Drives default doc/code scan paths. |
| `OPENAI_API_KEY` | optional | services/kb.py:48, main.py:265 | Required for OpenAI embedding fallback and debug endpoint signal. |
| `OPENAI_EMBEDDINGS_MODEL` | default `text-embedding-3-small` | services/kb.py:49 | Chosen when fallback kicks in. |
| `KB_EMBED_DIM` | optional | services/kb.py:63 | Validates persisted index dimension. |
| `KB_MAX_FILE_SIZE_MB` | default `2` | services/kb.py:98 | Skip oversized files during indexing. |
| `SEMANTIC_DEFAULT_K` | default `6` | services/semantic_retriever.py:32 | Default document count per tier. |
| `WIPE_INDEX` | default `false` | services/kb.py:246, services/indexer.py:66 | Deletes existing index before rebuild when set to `1/true`. |
| `GOOGLE_FOLDER_NAME` | default `COMMAND_CENTER` | services/google_docs_sync.py:41 | Drive folder to sync. |
| `GOOGLE_CREDS_JSON` | required for docs sync | services/google_docs_sync.py:55 | Base64 service-account creds. |
| `GOOGLE_TOKEN_JSON` | optional | services/google_docs_sync.py:65 | Base64 cached OAuth token. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | optional | main.py:113 | Enables OpenTelemetry export if set. |
| `GIT_COMMIT` / `APP_ENV` | optional | main.py:108 | Logged during startup for traceability. |

## Quickstart
- Python 3.11+, Node 18+.
- `pip install -r requirements.txt`
- `npm install` inside `frontend/` if you need the UI.
- Populate `.env` with at least `API_KEY` and any Google/OpenAI credentials you expect to use.

### Run locally
- Backend: `uvicorn main:app --reload`
- Frontend: `cd frontend && npm run dev`
- The FastAPI app listens on `http://127.0.0.1:8000` by default.

### Docs Sync
```
curl -X POST \
  -H "X-API-Key: $API_KEY" \
  http://127.0.0.1:8000/docs/sync
```
> `X-API-Key` is currently ignored because `require_api_key()` is a stub (routes/docs.py:56). Successful execution still requires Google credentials, and will fail once `kb.api_reindex()` raises.

### Simple /ask smoke test
```
curl -X POST http://127.0.0.1:8000/ask \
  -H 'content-type: application/json' \
  -d '{"query": "Ping"}'
```
> Expect a 400 if the query is shorter than 3 characters, or a 500 if the MCP agent cannot be imported.

## Operations
### Sync docs
1. Ensure `GOOGLE_CREDS_JSON` (and optionally `GOOGLE_TOKEN_JSON`) are set.
2. POST `/docs/sync` (see curl above) to pull Drive docs into `docs/imported/`.
3. Inspect output files and `docs/imported/` timestamps; `kb.api_reindex()` currently throws `AttributeError`, so KB refresh must be handled manually via `services.kb.embed_all()` until fixed.

### Validate KB/Search
1. `python -m services.kb health` verifies index presence and dimension (requires llama-index deps).
2. `python -m services.kb search "status endpoint"` returns sample matches; empty output indicates missing index.
3. `GET /mcp/diag` confirms agents and retrievers import cleanly; `GET /mcp/diag_ctx` exercises context assembly.

## Troubleshooting
- **401 on `/control/*`** – Missing or wrong `X-API-Key` header (`routes/control.py:42`).
- **401/500 on docs routes** – Google credentials absent or `kb.api_reindex()` undefined (`routes/docs.py:115`, `services/kb.py` lacks the method).
- **501 from `/ask/*_stream`** – Corresponding agent module missing (`routes/ask.py:747`, `routes/ask.py:788`).
- **504 responses** – Request exceeded `HTTP_TIMEOUT_S` or MCP agent timeout (`main.py:171`, `routes/mcp.py:365`).
- **404 from `/docs/view`** – Path not inside `/docs` (`routes/docs.py:98`) or file missing.

## Known Limitations / TODOs
- `require_api_key()` in docs router is a no-op; tighten once auth is defined (`routes/docs.py:56`).
- `kb.api_reindex()` is referenced but not implemented, so every docs reindex call raises (`routes/docs.py:115` vs. `services/kb.py`).
- `ContextEngine.clear_cache()` is stubbed to a no-op (`services/context_engine.py:14`), so cache invalidation does nothing.
- `/control/write_file` writes directly into the repo; guard the action queue appropriately.
- Many routers listed in `routes/` are intentionally disabled; re-enable by uncommenting in `main.py` once verified.

## Contributing / Dev Tips
- Keep router additions explicit in `main.py` to avoid accidentally exposing unfinished endpoints.
- KB builds rely on llama-index; run `python -m services.kb embed` after adjusting doc paths.
- Control queue state lives under `data/pending_actions.json` and `logs/actions.log`; clean them between local runs if needed.
- Use `/mcp/diag` and `/mcp/diag_ctx` to triage agent import or context issues before touching `/ask`.

## License
No license file is present; treat as proprietary until clarified.

## Operations

### Docs → KB Operations (Runbook Excerpt)

Paste this section into your repo’s README.md under “Operations”. It documents how the Docs → KB pipeline works end-to-end, what to configure, and how to operate it safely in prod.

── Overview

The Docs pipeline ingests Markdown from docs/ (and Google Docs via optional sync), refreshes the KB index, and exposes read/search endpoints. It’s production-hardened with auth, CORS normalization, concurrency locks, async wait=, cache invalidation, and a /readyz health probe.

[Google Docs] ──(optional sync)──> docs/imported/*.md
[Generated]  ────────────────────> docs/generated/*.md
                                            │
                                            ├─> /docs/refresh_kb → services/kb.api_reindex() → INDEX_ROOT
                                            └─> ContextEngine.clear_cache()  (real, tolerant)

── Environment & Config
Required (prod)

FRONTEND_ORIGINS — comma list of exact origins (e.g., https://relay.wildfireranch.us,https://status.wildfireranch.us)

One of API_KEY | RELAY_API_KEY | ADMIN_API_KEY — used as X-Api-Key

INDEX_ROOT — persistent, writable path for KB index

OPENAI_API_KEY — embedding/runtime (per your KB implementation)

KB_EMBED_MODEL — e.g., text-embedding-3-small

Google Docs (optional)

GOOGLE_CREDS_JSON — file path or base64 JSON to OAuth client

GOOGLE_TOKEN_JSON — file path or base64 JSON to user token (parent dir must be writable)

OAUTH_REDIRECT_URI — backend callback (recommended)

POST_AUTH_REDIRECT_URI — frontend landing page after auth (e.g., /docs)

Sensible defaults

ENV=prod in production; dev permits missing auth and uses http://localhost:3000 for CORS fallback.

Required directories are created on boot:

<PROJECT_ROOT>/docs/imported

<PROJECT_ROOT>/docs/generated

INDEX_ROOT

── Authentication & CORS

All mutating Docs/KB routes require X-Api-Key ∈ { API_KEY, RELAY_API_KEY, ADMIN_API_KEY }.

CORS is list-only: FRONTEND_ORIGINS (no regex in prod). Logged once at startup and hard-fails if missing in prod.

── Concurrency & Async Behavior

Long-running ops are protected by inter-process locks under var/locks/:

Locks: docs_sync, docs_full_sync, kb_reindex, docs_prune

Query param wait=true|false (default true)

wait=true → do work inline; returns final payload (200 or 503/409/500)

wait=false → queued via BackgroundTasks; returns 202 {"accepted": true}

HTTP 409 is returned if a competing operation holds the lock.

── Endpoints (Backend)
Route	Method	Auth	Notes
/docs/list	GET	✅	List docs with basic metadata
/docs/view?path=…	GET	✅	Return raw Markdown (path traversal safe)
/docs/sync?wait=	POST	✅	Optional Google sync → files; 503 when stack disabled
/docs/refresh_kb?wait=	POST	✅	Reindex KB via services/kb.api_reindex()
/docs/full_sync?wait=	POST	✅	Google sync + KB reindex (composed)
/docs/promote	POST	✅	Promote variant to canonical id path + reindex
/docs/prune_duplicates?wait=	POST	✅	Remove dupes + reindex
/docs/mark_priority	POST	✅	Update metadata (tier/pinned) + reindex
/kb/search	GET/POST	✅	KB query (payload vs querystring)
/kb/reindex	POST	✅	Optional direct KB refresh (same semantics)
/kb/summary	GET	⚠️	Consider guarding if it reveals sensitive data
/readyz	GET	❌	Readiness probe (read-only, safe for unauthenticated use)

Auth note: “✅” → requires X-Api-Key. /readyz is intentionally public (non-mutating).

── Frontend Proxies (Next.js)

The UI calls server-side proxies under /api/docs/* which inject X-Api-Key from server env (no secret in browser). Typical files:

frontend/src/app/api/docs/list/route.ts
frontend/src/app/api/docs/view/route.ts
frontend/src/app/api/docs/sync/route.ts
frontend/src/app/api/docs/refresh_kb/route.ts
frontend/src/app/api/docs/full_sync/route.ts


On non-OK, proxies forward exact status/body so the UI displays actionable errors like:

409 … — docs_sync already in progress

503 … — Google client stack unavailable: No module named 'google'

── Readiness Probe

GET /readyz returns 200 when acceptable for current ENV, else 503 with reasons.

Example (prod, Google disabled intentionally):

{
  "ok": true,
  "env": "prod",
  "api_auth": "configured",
  "index_root": { "path": "/data/index", "writable": true },
  "google_stack": "disabled",
  "details": { "google": { "reason": "ModuleNotFoundError('No module named ...')" } },
  "problems": []
}


Failure (prod, auth missing or index unwritable) adds "problems": ["auth_missing","index_root_not_writable"].

── Smoke Tests (Copy/Paste)
API="${API_ROOT:-http://localhost:1455}"
KEY="$API_KEY"   # or RELAY_API_KEY / ADMIN_API_KEY

# List & view
curl -sS -H "X-Api-Key: $KEY" "$API/docs/list?category=all&limit=5" | jq .
curl -sS -H "X-Api-Key: $KEY" "$API/docs/view?path=generated/readme.md" | jq -r .content | head -n 20

# KB reindex (should return structured status)
curl -sS -X POST -H "X-Api-Key: $KEY" "$API/docs/refresh_kb" | jq .

# Sync (503 if Google stack disabled)
curl -sS -i -X POST -H "X-Api-Key: $KEY" "$API/docs/sync?wait=true"

# Background full sync
curl -sS -i -X POST -H "X-Api-Key: $KEY" "$API/docs/full_sync?wait=false"

# Prune duplicates (background)
curl -sS -i -X POST -H "X-Api-Key: $KEY" "$API/docs/prune_duplicates?wait=false"

# KB search
curl -sS -H "X-Api-Key: $KEY" "$API/kb/search?query=tarana&k=8" | jq .

# Readiness
curl -sS "$API/readyz" | jq .

── Troubleshooting (Fast Picks)

401 Unauthorized
Ensure the proxy sends X-Api-Key (server env has one of: ADMIN_API_KEY, RELAY_API_KEY, API_KEY).

503 Google stack unavailable
Install google-api-python-client, google-auth, google-auth-oauthlib, markdownify.
Set GOOGLE_CREDS_JSON & GOOGLE_TOKEN_JSON to file path or base64 JSON.
Confirm GOOGLE_TOKEN_JSON parent dir is writable (/data/secrets/... recommended).

409 already in progress
Another op holds the lock. Either call with wait=false or retry after it finishes.

KB reindex returns {ok:false}
Check OPENAI_API_KEY, KB_EMBED_MODEL, and INDEX_ROOT writability. See logs for the error class.

CORS errors in browser
Verify FRONTEND_ORIGINS includes the exact origin(s) of your frontend; no regex in prod.

── Observability

You should see structured logs like:

docs_sync / docs_full_sync / kb_reindex with duration_ms and counts

context_engine.clear_cache {cleared, version}

cors.origins [...]

paths_ready imported=… generated=… index_root=… writable=…

Consider exporting Prometheus counters later (e.g., ops success/failure by route and HTTP code).

── Rollback Notes

Feature-wise rollback is simple:

Revert the last deployment.

To disable Google sync only: leave routes mounted; the guarded import yields 503 (safe).

To disable KB writes temporarily: set the API to read-only in your ops UI and avoid calling /docs/* mutators.

── Appendix: Operator Checklist (Prod)

 FRONTEND_ORIGINS set to exact domains

 One of API_KEY|RELAY_API_KEY|ADMIN_API_KEY configured

 INDEX_ROOT mounted & writable (volume)

 OPENAI_API_KEY set; KB_EMBED_MODEL sensible

 (Optional) Google stack installed + creds/token envs wired

 /readyz returns 200 (or 200 with google_stack=disabled if sync is intentionally off)

 Smoke tests pass (above)
## Admin Ask (Safe Ask-Echo)

- Paths: `frontend/src/app/admin/ask/page.tsx` (UI), `frontend/src/app/api/ask/*` (proxies)
- Gate: `frontend/middleware.ts` protects `/admin/ask` and alias `/status/ask`.

Environment (server-side only):
- `NEXT_PUBLIC_API_URL` – base API URL (e.g., https://api.wildfireranch.us)
- `ADMIN_API_KEY` or `RELAY_API_KEY` or `API_KEY` – injected as `X-Api-Key`
- `ADMIN_UI_TOKEN` – Bearer token required by middleware
- `ADMIN_IPS` (optional) – comma-separated IP allowlist (e.g., `203.0.113.10,198.51.100.25`)

Security Notes:
- Browser never contacts the backend API directly; it calls `/api/ask/*` proxies.
- Proxies inject `X-Api-Key` from server env; secrets never render client-side or in logs.
- Edge Middleware enforces IP allowlist (if set) and `Authorization: Bearer <ADMIN_UI_TOKEN>`.
- Page is hidden and `noindex` via `metadata`.

Test with curl:
```
FRONTEND=http://localhost:3000
TOKEN='<ADMIN_UI_TOKEN>'

# Gate checks
curl -i "$FRONTEND/admin/ask" | head -n2                  # 401
curl -i -H "Authorization: Bearer $TOKEN" "$FRONTEND/admin/ask" | head -n2    # 200 if IP allowed

# Proxy check (server adds X-Api-Key)
curl -i -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "$FRONTEND/api/ask/run" --data '{"question":"ping"}'    # mirrors upstream status/body
```

Rollback:
- Remove `frontend/middleware.ts`
- Remove `frontend/src/app/api/ask/run/route.ts`
- Remove `frontend/src/app/api/ask/stream/route.ts` (if not needed)
- Remove `frontend/src/app/admin/ask/page.tsx`
