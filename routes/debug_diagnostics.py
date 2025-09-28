# ──────────────────────────────────────────────────────────────────────────────
# File: routes/debug_diagnostics.py
# Purpose: Isolated diagnostic endpoints to test each service independently
#          for debugging pipeline connectivity issues
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import asyncio
import os
import time
import traceback
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from utils.async_helpers import maybe_await

# Router
router = APIRouter(prefix="/debug", tags=["diagnostics"])

# Logging
try:
    from core.logging import log_event  # type: ignore
except Exception:
    def log_event(event: str, data: Optional[Dict[str, Any]] = None) -> None:
        pass

# ──────────────────────────────────────────────────────────────────────────────
# KB Service Direct Test
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/kb-direct")
async def debug_kb_direct(
    query: str = Query(..., description="Search query"),
    k: int = Query(5, description="Number of results"),
    request: Request = None
):
    """Test KB search functionality directly without pipeline orchestration."""
    corr_id = uuid4().hex
    start_time = time.perf_counter()

    log_event("debug_kb_direct_start", {
        "corr_id": corr_id,
        "query": query,
        "k": k
    })

    try:
        # Test services.kb import
        log_event("debug_kb_import_attempt", {"corr_id": corr_id})
        try:
            from services import kb
            log_event("debug_kb_import_success", {"corr_id": corr_id})
        except Exception as e:
            log_event("debug_kb_import_failed", {
                "corr_id": corr_id,
                "error": str(e),
                "traceback": traceback.format_exc()
            })
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "kb_import_failed",
                    "message": str(e),
                    "step": "importing_kb_service"
                }
            )

        # Test kb.search function availability
        if not hasattr(kb, 'search'):
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "kb_search_unavailable",
                    "message": "KB service has no search method",
                    "available_methods": [attr for attr in dir(kb) if not attr.startswith('_')]
                }
            )

        # Attempt KB search
        log_event("debug_kb_search_attempt", {
            "corr_id": corr_id,
            "query_length": len(query)
        })

        search_result = await maybe_await(kb.search, query=query, k=k)

        elapsed = time.perf_counter() - start_time

        log_event("debug_kb_direct_success", {
            "corr_id": corr_id,
            "elapsed_ms": elapsed * 1000,
            "result_type": type(search_result).__name__,
            "result_length": len(str(search_result))
        })

        return {
            "success": True,
            "corr_id": corr_id,
            "elapsed_ms": elapsed * 1000,
            "query": query,
            "k": k,
            "result": search_result,
            "result_type": type(search_result).__name__
        }

    except Exception as e:
        elapsed = time.perf_counter() - start_time

        log_event("debug_kb_direct_failed", {
            "corr_id": corr_id,
            "elapsed_ms": elapsed * 1000,
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc()
        })

        raise HTTPException(
            status_code=500,
            detail={
                "error": "kb_search_failed",
                "message": str(e),
                "corr_id": corr_id,
                "elapsed_ms": elapsed * 1000,
                "traceback": traceback.format_exc()
            }
        )

# ──────────────────────────────────────────────────────────────────────────────
# Semantic Retriever Direct Test
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/semantic-direct")
async def debug_semantic_direct(
    query: str = Query(..., description="Search query"),
    tier: str = Query("global", description="Retrieval tier"),
    k: int = Query(5, description="Number of results"),
    request: Request = None
):
    """Test semantic retrieval functionality directly."""
    corr_id = uuid4().hex
    start_time = time.perf_counter()

    log_event("debug_semantic_direct_start", {
        "corr_id": corr_id,
        "query": query,
        "tier": tier,
        "k": k
    })

    try:
        # Test semantic_retriever import
        log_event("debug_semantic_import_attempt", {"corr_id": corr_id})
        try:
            from services.semantic_retriever import SemanticRetriever, TieredSemanticRetriever
            log_event("debug_semantic_import_success", {"corr_id": corr_id})
        except Exception as e:
            log_event("debug_semantic_import_failed", {
                "corr_id": corr_id,
                "error": str(e),
                "traceback": traceback.format_exc()
            })
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "semantic_import_failed",
                    "message": str(e),
                    "step": "importing_semantic_retriever"
                }
            )

        # Create retriever instance
        log_event("debug_semantic_create_retriever", {"corr_id": corr_id, "tier": tier})

        score_thresh_env = os.getenv("SEMANTIC_SCORE_THRESHOLD")
        score_thresh = float(score_thresh_env) if score_thresh_env else None

        retriever = TieredSemanticRetriever(tier, score_threshold=score_thresh)

        # Attempt search
        log_event("debug_semantic_search_attempt", {
            "corr_id": corr_id,
            "query_length": len(query),
            "score_threshold": score_thresh
        })

        search_result = await maybe_await(retriever.search, query=query, k=k)

        elapsed = time.perf_counter() - start_time

        log_event("debug_semantic_direct_success", {
            "corr_id": corr_id,
            "elapsed_ms": elapsed * 1000,
            "result_type": type(search_result).__name__,
            "result_count": len(search_result) if isinstance(search_result, list) else 0
        })

        return {
            "success": True,
            "corr_id": corr_id,
            "elapsed_ms": elapsed * 1000,
            "query": query,
            "tier": tier,
            "k": k,
            "score_threshold": score_thresh,
            "result": search_result,
            "result_count": len(search_result) if isinstance(search_result, list) else 0
        }

    except Exception as e:
        elapsed = time.perf_counter() - start_time

        log_event("debug_semantic_direct_failed", {
            "corr_id": corr_id,
            "elapsed_ms": elapsed * 1000,
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc()
        })

        raise HTTPException(
            status_code=500,
            detail={
                "error": "semantic_search_failed",
                "message": str(e),
                "corr_id": corr_id,
                "elapsed_ms": elapsed * 1000,
                "traceback": traceback.format_exc()
            }
        )

# ──────────────────────────────────────────────────────────────────────────────
# Context Engine Direct Test
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/context-build")
async def debug_context_build(
    query: str = Query(..., description="Search query"),
    request: Request = None
):
    """Test context engine build_context functionality directly."""
    corr_id = uuid4().hex
    start_time = time.perf_counter()

    log_event("debug_context_build_start", {
        "corr_id": corr_id,
        "query": query
    })

    try:
        # Test context_engine import
        log_event("debug_context_engine_import_attempt", {"corr_id": corr_id})
        try:
            import importlib
            ctx_mod = importlib.import_module("core.context_engine")
            build_context = getattr(ctx_mod, "build_context", None)
            ContextRequest = getattr(ctx_mod, "ContextRequest", None)
            EngineConfig = getattr(ctx_mod, "EngineConfig", None)
            RetrievalTier = getattr(ctx_mod, "RetrievalTier", None)
            TierConfig = getattr(ctx_mod, "TierConfig", None)

            log_event("debug_context_engine_import_success", {
                "corr_id": corr_id,
                "build_context_available": callable(build_context),
                "classes_available": None not in {ContextRequest, EngineConfig, RetrievalTier, TierConfig}
            })

        except Exception as e:
            log_event("debug_context_engine_import_failed", {
                "corr_id": corr_id,
                "error": str(e),
                "traceback": traceback.format_exc()
            })
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "context_engine_import_failed",
                    "message": str(e),
                    "step": "importing_context_engine"
                }
            )

        if not callable(build_context) or None in {ContextRequest, EngineConfig, RetrievalTier, TierConfig}:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "context_engine_unavailable",
                    "message": "Context engine components not available",
                    "build_context_callable": callable(build_context),
                    "missing_classes": [name for name, cls in {
                        "ContextRequest": ContextRequest,
                        "EngineConfig": EngineConfig,
                        "RetrievalTier": RetrievalTier,
                        "TierConfig": TierConfig
                    }.items() if cls is None]
                }
            )

        # Test semantic retriever import for context engine
        log_event("debug_context_semantic_import", {"corr_id": corr_id})
        try:
            from services.semantic_retriever import TieredSemanticRetriever
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "semantic_retriever_import_failed",
                    "message": str(e),
                    "step": "importing_semantic_for_context"
                }
            )

        # Build minimal context configuration
        log_event("debug_context_config_build", {"corr_id": corr_id})

        score_thresh_env = os.getenv("SEMANTIC_SCORE_THRESHOLD")
        score_thresh = float(score_thresh_env) if score_thresh_env else None

        retrievers = {
            RetrievalTier.GLOBAL: TieredSemanticRetriever("global", score_threshold=score_thresh),
            RetrievalTier.PROJECT_DOCS: TieredSemanticRetriever("project_docs", score_threshold=score_thresh),
        }

        tier_overrides = {
            RetrievalTier.GLOBAL: TierConfig(top_k=6, min_score=0.35),
            RetrievalTier.PROJECT_DOCS: TierConfig(top_k=6, min_score=0.35),
        }

        default_tier = TierConfig(top_k=6, min_score=0.35)

        cfg = EngineConfig(
            retrievers=retrievers,
            tier_overrides=tier_overrides,
            default_tier=default_tier,
            max_context_tokens=2400,
            token_counter=None,
        )

        # Attempt context build
        log_event("debug_context_execute", {"corr_id": corr_id})

        ctx_result = build_context(ContextRequest(query=query, corr_id=corr_id), cfg)

        elapsed = time.perf_counter() - start_time

        context_text = str((ctx_result or {}).get("context") or "")
        files_used = (ctx_result or {}).get("files_used") or []
        kb_meta = ((ctx_result or {}).get("meta") or {}).get("kb") or {}
        matches = (ctx_result or {}).get("matches") or []

        log_event("debug_context_build_success", {
            "corr_id": corr_id,
            "elapsed_ms": elapsed * 1000,
            "context_length": len(context_text),
            "files_used_count": len(files_used),
            "kb_hits": int(kb_meta.get("hits") or 0),
            "matches_count": len(matches)
        })

        return {
            "success": True,
            "corr_id": corr_id,
            "elapsed_ms": elapsed * 1000,
            "query": query,
            "context_length": len(context_text),
            "files_used_count": len(files_used),
            "kb_meta": kb_meta,
            "matches_count": len(matches),
            "score_threshold": score_thresh,
            "result": {
                "context": context_text[:500] + "..." if len(context_text) > 500 else context_text,
                "files_used": files_used,
                "kb": kb_meta,
                "matches": matches[:3]  # First 3 matches for brevity
            }
        }

    except Exception as e:
        elapsed = time.perf_counter() - start_time

        log_event("debug_context_build_failed", {
            "corr_id": corr_id,
            "elapsed_ms": elapsed * 1000,
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc()
        })

        raise HTTPException(
            status_code=500,
            detail={
                "error": "context_build_failed",
                "message": str(e),
                "corr_id": corr_id,
                "elapsed_ms": elapsed * 1000,
                "traceback": traceback.format_exc()
            }
        )

# ──────────────────────────────────────────────────────────────────────────────
# MCP Agent Direct Test
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/mcp-ping")
async def debug_mcp_ping(
    request: Request = None
):
    """Test MCP agent basic functionality and imports."""
    corr_id = uuid4().hex
    start_time = time.perf_counter()

    log_event("debug_mcp_ping_start", {"corr_id": corr_id})

    try:
        # Test mcp_agent import
        log_event("debug_mcp_import_attempt", {"corr_id": corr_id})
        try:
            from agents.mcp_agent import run_mcp
            log_event("debug_mcp_import_success", {"corr_id": corr_id})
        except Exception as e:
            log_event("debug_mcp_import_failed", {
                "corr_id": corr_id,
                "error": str(e),
                "traceback": traceback.format_exc()
            })
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "mcp_import_failed",
                    "message": str(e),
                    "step": "importing_mcp_agent"
                }
            )

        # Test basic MCP call with minimal payload
        log_event("debug_mcp_execute_attempt", {"corr_id": corr_id})

        mcp_result = await maybe_await(
            run_mcp,
            query="ping",
            role="planner",
            files=[],
            topics=[],
            user_id="debug",
            debug=True,
            corr_id=corr_id,
            context="",
            timeout_s=30,
        )

        elapsed = time.perf_counter() - start_time

        log_event("debug_mcp_ping_success", {
            "corr_id": corr_id,
            "elapsed_ms": elapsed * 1000,
            "result_type": type(mcp_result).__name__,
            "result_size": len(str(mcp_result)) if mcp_result else 0
        })

        return {
            "success": True,
            "corr_id": corr_id,
            "elapsed_ms": elapsed * 1000,
            "mcp_available": True,
            "result": mcp_result,
            "result_type": type(mcp_result).__name__
        }

    except Exception as e:
        elapsed = time.perf_counter() - start_time

        log_event("debug_mcp_ping_failed", {
            "corr_id": corr_id,
            "elapsed_ms": elapsed * 1000,
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc()
        })

        raise HTTPException(
            status_code=500,
            detail={
                "error": "mcp_ping_failed",
                "message": str(e),
                "corr_id": corr_id,
                "elapsed_ms": elapsed * 1000,
                "traceback": traceback.format_exc()
            }
        )

# ──────────────────────────────────────────────────────────────────────────────
# Environment & Configuration Test
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/env-config")
async def debug_env_config(
    request: Request = None
):
    """Test environment configuration and key variables."""
    corr_id = uuid4().hex

    log_event("debug_env_config_start", {"corr_id": corr_id})

    try:
        env_vars = {
            "SEMANTIC_SCORE_THRESHOLD": os.getenv("SEMANTIC_SCORE_THRESHOLD"),
            "RERANK_MIN_SCORE_GLOBAL": os.getenv("RERANK_MIN_SCORE_GLOBAL"),
            "TOPK_GLOBAL": os.getenv("TOPK_GLOBAL"),
            "TOPK_PROJECT_DOCS": os.getenv("TOPK_PROJECT_DOCS"),
            "MAX_CONTEXT_TOKENS": os.getenv("MAX_CONTEXT_TOKENS"),
            "KB_EMBED_MODEL": os.getenv("KB_EMBED_MODEL"),
            "OPENAI_API_KEY": "present" if os.getenv("OPENAI_API_KEY") else "missing",
            "INDEX_ROOT": os.getenv("INDEX_ROOT"),
            "ENV": os.getenv("ENV"),
        }

        # Test critical path imports
        import_tests = {}

        # Test core imports
        try:
            import core.context_engine
            import_tests["core.context_engine"] = "success"
        except Exception as e:
            import_tests["core.context_engine"] = f"failed: {str(e)}"

        try:
            import services.semantic_retriever
            import_tests["services.semantic_retriever"] = "success"
        except Exception as e:
            import_tests["services.semantic_retriever"] = f"failed: {str(e)}"

        try:
            import services.kb
            import_tests["services.kb"] = "success"
        except Exception as e:
            import_tests["services.kb"] = f"failed: {str(e)}"

        try:
            import agents.mcp_agent
            import_tests["agents.mcp_agent"] = "success"
        except Exception as e:
            import_tests["agents.mcp_agent"] = f"failed: {str(e)}"

        log_event("debug_env_config_success", {
            "corr_id": corr_id,
            "env_vars_count": len([v for v in env_vars.values() if v]),
            "import_success_count": len([t for t in import_tests.values() if t == "success"])
        })

        return {
            "success": True,
            "corr_id": corr_id,
            "env_vars": env_vars,
            "import_tests": import_tests,
            "critical_imports_ok": all(t == "success" for t in import_tests.values())
        }

    except Exception as e:
        log_event("debug_env_config_failed", {
            "corr_id": corr_id,
            "error": str(e),
            "traceback": traceback.format_exc()
        })

        raise HTTPException(
            status_code=500,
            detail={
                "error": "env_config_failed",
                "message": str(e),
                "corr_id": corr_id,
                "traceback": traceback.format_exc()
            }
        )

# ──────────────────────────────────────────────────────────────────────────────
# Utility Functions
# ──────────────────────────────────────────────────────────────────────────────

