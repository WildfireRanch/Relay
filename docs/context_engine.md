# `context_engine.py`

**Directory**: `services`
**Purpose**: # Purpose: Manages the creation and lifecycle of context objects, including caching mechanisms, for the application.

## Upstream
- ENV: —
- Imports: services.context_injector

## Downstream
- routes.docs
- services.agent

## Contents
- `ContextEngine()`
- `build()`
- `clear_cache()`