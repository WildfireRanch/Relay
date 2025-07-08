# `main.py`

**Directory**: `.`
**Purpose**: # Purpose: Serve as the entry point for the web application, initializing the server and routing requests to appropriate handlers.

## Upstream
- ENV: ENV, FRONTEND_ORIGIN_REGEX, FRONTEND_ORIGIN, ENV, JAEGER_HOST, JAEGER_PORT, PORT, ENABLE_ADMIN_TOOLS
- Imports: __future__, os, logging, sys, pathlib, fastapi, fastapi.middleware.cors, fastapi.responses, routes.ask, routes.status, routes.control, routes.docs, routes.oauth, routes.debug, routes.kb, routes.search, routes.admin, routes.codex, routes.mcp, routes.logs, services, opentelemetry, opentelemetry.sdk.resources, opentelemetry.sdk.trace, opentelemetry.sdk.trace.export, opentelemetry.exporter.jaeger.thrift, opentelemetry.instrumentation.fastapi, uvicorn, dotenv, subprocess

## Downstream
- —

## Contents
- `ensure_kb_index()`
- `health_check()`
- `root()`
- `test_cors()`
- `version()`