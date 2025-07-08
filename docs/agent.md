# `agent.py`

**Directory**: `services`
**Purpose**: # Purpose: Provides functionalities for automated documentation generation, code review, and interaction with knowledge base services.

## Upstream
- ENV: API_KEY, RAILWAY_URL, ENABLE_REFLECT_AND_PLAN
- Imports: os, re, json, pathlib, typing, openai, services.kb, httpx, services.context_engine, utils.openai_client

## Downstream
- —

## Contents
- `answer()`
- `gen()`
- `generate_doc_for_path()`
- `reflect_and_plan()`
- `run_code_review()`
- `search_docs()`
- `wants_docgen()`