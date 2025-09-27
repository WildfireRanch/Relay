# Relay Command Center - API Endpoints Documentation

This document provides comprehensive documentation for all available API endpoints in the Relay Command Center backend.

## Base Information

- **Base URL**: `https://your-railway-app.railway.app` or your custom domain
- **API Version**: v1
- **Content Type**: `application/json`
- **Authentication**: API Key via `X-API-Key` header (where required)

## Authentication

Most endpoints require authentication via the `X-API-Key` header:

```bash
curl -H "X-API-Key: your-api-key" https://api.yourdomain.com/endpoint
```

Authentication levels:
- 🔓 **None**: No authentication required
- 🔐 **API Key**: Requires `X-API-Key` header
- ⚠️ **Stub**: Authentication implemented but currently bypassed

## Health & Status Endpoints

### Liveness Probe
```http
GET /Live
```

**Description**: Basic liveness check for the application.

**Authentication**: 🔓 None

**Response**:
```json
{
  "ok": true
}
```

### Readiness Probe
```http
GET /Ready
```

**Description**: Readiness check with dependency validation.

**Authentication**: 🔓 None

**Response**:
```json
{
  "ok": true,
  "env": "production",
  "api_auth": "configured",
  "index_root": {
    "path": "/data/index",
    "writable": true
  },
  "google_stack": "enabled",
  "problems": []
}
```

### Debug API Key Status
```http
GET /gh/debug/api-key
```

**Description**: Reports whether required API keys are configured.

**Authentication**: 🔓 None

**Response**:
```json
{
  "openai_api_key_present": true,
  "github_app_id_present": false
}
```

## Ask & Agent Endpoints

### Main Ask Endpoint
```http
POST /ask
```

**Description**: Main MCP pipeline with retrieval gate and anti-parrot checks.

**Authentication**: 🔓 None

**Request Body**:
```json
{
  "query": "Your question here",
  "context": "Optional additional context",
  "options": {
    "timeout": 60,
    "safe_mode": false
  }
}
```

**Response**:
```json
{
  "response": "Agent response",
  "meta": {
    "request_id": "uuid",
    "latency_ms": 1500,
    "origin": "mcp_agent"
  },
  "context": "Retrieved context used"
}
```

**Error Responses**:
- `400`: Query too short (< 3 characters)
- `500`: MCP agent import failure
- `504`: Request timeout

### Ask Options (CORS Preflight)
```http
OPTIONS /ask
```

**Description**: CORS preflight handler.

**Authentication**: 🔓 None

**Response**: `204 No Content`

### Legacy Ask (GET)
```http
GET /ask?query=your+question
```

**Description**: Legacy query parameter interface that dispatches to POST handler.

**Authentication**: 🔓 None

### Stream Ask
```http
POST /ask/stream
```

**Description**: Streams text responses via echo agent.

**Authentication**: 🔓 None

**Request Body**:
```json
{
  "query": "Your question",
  "stream": true
}
```

**Response**: Server-Sent Events (SSE) stream

**Error Response**:
- `501`: Echo agent not available

### Codex Stream
```http
POST /ask/codex_stream
```

**Description**: Streams code patches via codex agent.

**Authentication**: 🔓 None

**Request Body**:
```json
{
  "query": "Code modification request",
  "context": "Current code context"
}
```

**Response**: Server-Sent Events (SSE) stream

**Error Response**:
- `501`: Codex agent not available

## MCP (Model Control Protocol) Endpoints

### MCP Ping
```http
GET /mcp/ping
```

**Description**: Lightweight status check for MCP stack.

**Authentication**: 🔓 None

**Response**:
```json
{
  "status": "ok",
  "safe_mode": false,
  "agents_available": ["mcp_agent", "echo_agent"]
}
```

### MCP Diagnostics
```http
GET /mcp/diag
```

**Description**: Lists filesystem/import status for agents and retrievers.

**Authentication**: 🔓 None

**Response**:
```json
{
  "agents": {
    "mcp_agent": {
      "status": "available",
      "path": "/app/agents/mcp_agent.py"
    },
    "echo_agent": {
      "status": "missing",
      "error": "Import error"
    }
  },
  "retrievers": {
    "semantic_retriever": {
      "status": "available",
      "backend": "llamaindex"
    }
  }
}
```

### MCP Context Diagnostics
```http
GET /mcp/diag_ctx
```

**Description**: Builds context using tiered retrievers and returns errors inline.

**Authentication**: 🔓 None

**Response**:
```json
{
  "context_built": true,
  "retrievers_used": ["semantic", "keyword"],
  "total_chunks": 15,
  "errors": []
}
```

### MCP Run
```http
POST /mcp/run
```

**Description**: Executes MCP agent with optional safe-mode fallback.

**Authentication**: 🔓 None

**Request Body**:
```json
{
  "query": "Your request",
  "context": "Additional context",
  "safe_mode": false
}
```

**Response**:
```json
{
  "result": "Agent execution result",
  "agent_used": "mcp_agent",
  "execution_time_ms": 2500
}
```

## Control Queue Endpoints

All control endpoints require authentication via `X-API-Key` header.

### Queue Action
```http
POST /control/queue_action
```

**Description**: Enqueues a pending action in the action queue.

**Authentication**: 🔐 API Key

**Request Body**:
```json
{
  "action_type": "file_write",
  "payload": {
    "path": "docs/example.md",
    "content": "File content"
  },
  "metadata": {
    "requester": "user_id",
    "reason": "Documentation update"
  }
}
```

**Response**:
```json
{
  "action_id": "uuid",
  "status": "queued",
  "timestamp": "2024-01-01T12:00:00Z"
}
```

### List Queue
```http
GET /control/list_queue
```

**Description**: Returns all pending actions in the queue.

**Authentication**: 🔐 API Key

**Response**:
```json
{
  "pending_actions": [
    {
      "action_id": "uuid",
      "action_type": "file_write",
      "status": "pending",
      "queued_at": "2024-01-01T12:00:00Z",
      "payload": {...}
    }
  ],
  "total_count": 1
}
```

### Approve Action
```http
POST /control/approve_action
```

**Description**: Executes a queued action via agent dispatch.

**Authentication**: 🔐 API Key

**Request Body**:
```json
{
  "action_id": "uuid"
}
```

**Response**:
```json
{
  "action_id": "uuid",
  "status": "executed",
  "result": "Action completed successfully",
  "executed_at": "2024-01-01T12:05:00Z"
}
```

### Deny Action
```http
POST /control/deny_action
```

**Description**: Marks an action as denied and logs the outcome.

**Authentication**: 🔐 API Key

**Request Body**:
```json
{
  "action_id": "uuid",
  "reason": "Security concern"
}
```

**Response**:
```json
{
  "action_id": "uuid",
  "status": "denied",
  "denied_at": "2024-01-01T12:05:00Z"
}
```

### Action Log
```http
GET /control/list_log
```

**Description**: Streams JSONL history from action log file.

**Authentication**: 🔐 API Key

**Response**: JSONL stream of historical actions

### Write File
```http
POST /control/write_file
```

**Description**: Directly writes a file relative to repository root.

**Authentication**: 🔐 API Key

**Request Body**:
```json
{
  "path": "relative/path/to/file.txt",
  "content": "File content",
  "mode": "create_or_overwrite"
}
```

**Response**:
```json
{
  "success": true,
  "path": "relative/path/to/file.txt",
  "bytes_written": 123
}
```

### Test Control Agent
```http
POST /control/test
```

**Description**: Direct call into control agent for manual execution.

**Authentication**: 🔐 API Key

**Request Body**:
```json
{
  "command": "test_command",
  "parameters": {...}
}
```

## Docs Management Endpoints

All docs endpoints currently use stub authentication (⚠️).

### List Documents
```http
GET /docs/list
```

**Description**: Enumerates markdown files under docs/imported and docs/generated.

**Authentication**: ⚠️ Stub

**Query Parameters**:
- `category` (optional): Filter by category (`imported`, `generated`, `all`)
- `limit` (optional): Limit number of results

**Response**:
```json
{
  "documents": [
    {
      "path": "imported/example.md",
      "title": "Example Document",
      "size": 1024,
      "modified": "2024-01-01T12:00:00Z",
      "category": "imported"
    }
  ],
  "total_count": 1
}
```

### View Document
```http
GET /docs/view?path=relative/path.md
```

**Description**: Returns file content if path resolves inside /docs directory.

**Authentication**: ⚠️ Stub

**Query Parameters**:
- `path` (required): Relative path to document

**Response**:
```json
{
  "content": "Document content in markdown",
  "metadata": {
    "path": "relative/path.md",
    "size": 1024,
    "modified": "2024-01-01T12:00:00Z"
  }
}
```

**Error Response**:
- `404`: File not found or path outside /docs

### Sync Documents
```http
POST /docs/sync
```

**Description**: Runs Google Drive sync then triggers KB reindex and cache clear.

**Authentication**: ⚠️ Stub

**Response**:
```json
{
  "sync_completed": true,
  "files_synced": 5,
  "kb_reindex_status": "completed",
  "cache_cleared": true
}
```

**Error Response**:
- `500`: Google Drive sync failure or KB reindex error

### Refresh Knowledge Base
```http
POST /docs/refresh_kb
```

**Description**: Calls KB reindex function only.

**Authentication**: ⚠️ Stub

**Response**:
```json
{
  "reindex_completed": true,
  "documents_processed": 25,
  "index_size_mb": 15.6
}
```

**Error Response**:
- `500`: KB reindex function missing or failed

### Full Sync
```http
POST /docs/full_sync
```

**Description**: Combines docs sync and KB refresh operations.

**Authentication**: ⚠️ Stub

**Response**:
```json
{
  "sync_completed": true,
  "files_synced": 5,
  "reindex_completed": true,
  "documents_processed": 30
}
```

### Promote Document
```http
POST /docs/promote
```

**Description**: Copies selected document to canonical root and reindexes.

**Authentication**: ⚠️ Stub

**Request Body**:
```json
{
  "source_path": "imported/draft.md",
  "target_path": "canonical/final.md"
}
```

**Response**:
```json
{
  "promoted": true,
  "source_path": "imported/draft.md",
  "target_path": "canonical/final.md",
  "reindex_completed": true
}
```

### Prune Duplicates
```http
POST /docs/prune_duplicates
```

**Description**: Removes duplicate document IDs then reindexes.

**Authentication**: ⚠️ Stub

**Response**:
```json
{
  "duplicates_removed": 3,
  "documents_remaining": 27,
  "reindex_completed": true
}
```

### Mark Priority
```http
POST /docs/mark_priority
```

**Description**: Writes metadata block to document and reindexes.

**Authentication**: ⚠️ Stub

**Request Body**:
```json
{
  "document_path": "important/doc.md",
  "priority": "high",
  "pinned": true,
  "metadata": {
    "tier": 1,
    "tags": ["important", "reference"]
  }
}
```

**Response**:
```json
{
  "metadata_updated": true,
  "document_path": "important/doc.md",
  "reindex_completed": true
}
```

## Error Handling

### Common Error Codes

- `400 Bad Request`: Invalid request parameters or malformed JSON
- `401 Unauthorized`: Missing or invalid `X-API-Key` header
- `404 Not Found`: Endpoint or resource not found
- `429 Too Many Requests`: Rate limiting (if implemented)
- `500 Internal Server Error`: Server-side error or agent failure
- `501 Not Implemented`: Feature not available (missing agent/module)
- `503 Service Unavailable`: Dependency unavailable (Google stack, KB, etc.)
- `504 Gateway Timeout`: Request exceeded timeout limit

### Error Response Format

```json
{
  "error": {
    "code": "INVALID_QUERY",
    "message": "Query must be at least 3 characters long",
    "details": {
      "received_length": 2,
      "minimum_length": 3
    }
  },
  "request_id": "uuid"
}
```

## Rate Limiting

Currently no explicit rate limiting is implemented. Consider implementing rate limiting for production use based on:
- API key
- IP address
- Endpoint type (heavy vs light operations)

## SDK Examples

### Python
```python
import requests

class RelayClient:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.headers = {"X-API-Key": api_key}

    def ask(self, query, context=None):
        response = requests.post(
            f"{self.base_url}/ask",
            json={"query": query, "context": context},
            headers=self.headers
        )
        return response.json()

# Usage
client = RelayClient("https://api.yourdomain.com", "your-api-key")
result = client.ask("What is the status of the system?")
```

### JavaScript/TypeScript
```typescript
interface AskRequest {
  query: string;
  context?: string;
  options?: {
    timeout?: number;
    safe_mode?: boolean;
  };
}

class RelayClient {
  constructor(
    private baseUrl: string,
    private apiKey: string
  ) {}

  async ask(request: AskRequest) {
    const response = await fetch(`${this.baseUrl}/ask`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': this.apiKey,
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error(`API Error: ${response.status}`);
    }

    return response.json();
  }
}
```

### cURL Examples
```bash
# Basic ask request
curl -X POST https://api.yourdomain.com/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "System status check"}'

# Control queue with authentication
curl -X POST https://api.yourdomain.com/control/queue_action \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "action_type": "file_write",
    "payload": {
      "path": "test.txt",
      "content": "Hello World"
    }
  }'

# Health check
curl https://api.yourdomain.com/Ready
```

## Changelog & Versioning

This API documentation reflects the current state of the system. Key changes:
- v1.0: Initial API structure
- v1.1: Added MCP endpoints
- v1.2: Enhanced control queue functionality
- v1.3: Added docs management endpoints

For the most up-to-date endpoint information, refer to the route matrix in the main [README.md](../README.md).