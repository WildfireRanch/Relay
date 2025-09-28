# ──────────────────────────────────────────────────────────────────────────────
# File: routes/debug_flow_trace.py
# Purpose: Comprehensive flow tracing for FastAPI + LlamaIndex system diagnostics
# 
# This module adds detailed flow tracing at each major pipeline step to identify
# exactly where the ask.py → mcp_agent → context_engine → semantic_retriever
# pipeline breaks in the orchestration flow.
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import asyncio
import importlib
import inspect
import os
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Safe logging import
try:
    from core.logging import log_event
except Exception:
    import logging, json
    _LOG = logging.getLogger("relay.flow_trace")
    def log_event(event: str, data: Dict[str, Any] | None = None) -> None:
        payload = {"event": event, **(data or {})}
        try:
            _LOG.info(json.dumps(payload, default=str))
        except Exception:
            _LOG.info("event=%s data=%s", event, (data or {}))

router = APIRouter(prefix="/debug", tags=["debug", "flow-trace"])

class FlowTraceRequest(BaseModel):
    query: str = Field(default="test query", description="Query to trace through pipeline")
    enable_deep_trace: bool = Field(default=True, description="Enable deep tracing at each step")
    test_mode: bool = Field(default=False, description="Run in isolated test mode")

class FlowStep(BaseModel):
    step_name: str
    status: str  # "success", "error", "skipped"
    duration_ms: float
    error: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

class FlowTraceResponse(BaseModel):
    success: bool
    corr_id: str
    total_duration_ms: float
    steps: List[FlowStep]
    break_point: Optional[str] = None
    recommendations: List[str]

# ──────────────────────────────────────────────────────────────────────────────
# Core Flow Tracing Functions
# ──────────────────────────────────────────────────────────────────────────────

async def trace_ask_entry_point(query: str, corr_id: str) -> FlowStep:
    """Trace routes/ask.py entry point and validation"""
    start_time = time.perf_counter()
    
    try:
        log_event("flow_trace_ask_entry", {
            "corr_id": corr_id,
            "step": "ask_entry_point",
            "query_length": len(query)
        })
        
        # Test ask.py import and basic validation
        ask_module = importlib.import_module("routes.ask")
        
        # Check for key functions/classes
        required_attrs = ["router", "AskBody", "ask_sync"]
        missing_attrs = [attr for attr in required_attrs if not hasattr(ask_module, attr)]
        
        if missing_attrs:
            raise RuntimeError(f"Missing ask.py attributes: {missing_attrs}")
        
        duration = (time.perf_counter() - start_time) * 1000
        
        return FlowStep(
            step_name="ask_entry_point",
            status="success",
            duration_ms=duration,
            data={
                "module_path": str(ask_module.__file__),
                "available_attrs": [attr for attr in dir(ask_module) if not attr.startswith("_")],
                "query_validated": True
            }
        )
        
    except Exception as e:
        duration = (time.perf_counter() - start_time) * 1000
        log_event("flow_trace_ask_entry_error", {
            "corr_id": corr_id,
            "error": str(e),
            "traceback": traceback.format_exc()
        })
        
        return FlowStep(
            step_name="ask_entry_point",
            status="error",
            duration_ms=duration,
            error=str(e)
        )

async def trace_mcp_agent_invocation(query: str, corr_id: str) -> FlowStep:
    """Trace agents/mcp_agent.py run_mcp() invocation"""
    start_time = time.perf_counter()
    
    try:
        log_event("flow_trace_mcp_invocation", {
            "corr_id": corr_id,
            "step": "mcp_agent_invocation"
        })
        
        # Test mcp_agent import
        mcp_module = importlib.import_module("agents.mcp_agent")
        
        # Check for run_mcp function
        if not hasattr(mcp_module, "run_mcp"):
            raise RuntimeError("agents.mcp_agent missing run_mcp function")
        
        run_mcp = getattr(mcp_module, "run_mcp")
        
        # Analyze function signature
        sig = inspect.signature(run_mcp)
        is_async = inspect.iscoroutinefunction(run_mcp)
        
        # Test basic invocation (without full execution)
        test_kwargs = {
            "query": query,
            "role": "planner",
            "files": [],
            "topics": [],
            "user_id": "test_user",
            "debug": True,
            "corr_id": corr_id
        }
        
        # Filter kwargs to match function signature
        valid_kwargs = {}
        for param_name in sig.parameters.keys():
            if param_name in test_kwargs:
                valid_kwargs[param_name] = test_kwargs[param_name]
        
        duration = (time.perf_counter() - start_time) * 1000
        
        return FlowStep(
            step_name="mcp_agent_invocation",
            status="success",
            duration_ms=duration,
            data={
                "module_path": str(mcp_module.__file__),
                "function_signature": str(sig),
                "is_async": is_async,
                "valid_kwargs": list(valid_kwargs.keys()),
                "signature_match": True
            }
        )
        
    except Exception as e:
        duration = (time.perf_counter() - start_time) * 1000
        log_event("flow_trace_mcp_invocation_error", {
            "corr_id": corr_id,
            "error": str(e),
            "traceback": traceback.format_exc()
        })
        
        return FlowStep(
            step_name="mcp_agent_invocation",
            status="error",
            duration_ms=duration,
            error=str(e)
        )

async def trace_context_engine_build(query: str, corr_id: str) -> FlowStep:
    """Trace core/context_engine.py build_context() calls"""
    start_time = time.perf_counter()
    
    try:
        log_event("flow_trace_context_build", {
            "corr_id": corr_id,
            "step": "context_engine_build"
        })
        
        # Import context engine components
        ctx_module = importlib.import_module("core.context_engine")
        
        required_components = ["build_context", "ContextRequest", "EngineConfig", "RetrievalTier", "TierConfig"]
        missing_components = [comp for comp in required_components if not hasattr(ctx_module, comp)]
        
        if missing_components:
            raise RuntimeError(f"Missing context engine components: {missing_components}")
        
        build_context = getattr(ctx_module, "build_context")
        ContextRequest = getattr(ctx_module, "ContextRequest")
        EngineConfig = getattr(ctx_module, "EngineConfig")
        RetrievalTier = getattr(ctx_module, "RetrievalTier")
        TierConfig = getattr(ctx_module, "TierConfig")
        
        # Test context request creation
        try:
            test_request = ContextRequest(query=query, corr_id=corr_id)
        except Exception as e:
            raise RuntimeError(f"Failed to create ContextRequest: {e}")
        
        # Test basic configuration
        try:
            test_config = EngineConfig(retrievers={})
        except Exception as e:
            raise RuntimeError(f"Failed to create EngineConfig: {e}")
        
        duration = (time.perf_counter() - start_time) * 1000
        
        return FlowStep(
            step_name="context_engine_build",
            status="success",
            duration_ms=duration,
            data={
                "module_path": str(ctx_module.__file__),
                "available_components": [comp for comp in required_components if hasattr(ctx_module, comp)],
                "context_request_created": True,
                "engine_config_created": True,
                "build_context_callable": callable(build_context)
            }
        )
        
    except Exception as e:
        duration = (time.perf_counter() - start_time) * 1000
        log_event("flow_trace_context_build_error", {
            "corr_id": corr_id,
            "error": str(e),
            "traceback": traceback.format_exc()
        })
        
        return FlowStep(
            step_name="context_engine_build",
            status="error",
            duration_ms=duration,
            error=str(e)
        )

async def trace_semantic_retriever_operations(query: str, corr_id: str) -> FlowStep:
    """Trace services/semantic_retriever.py search() operations"""
    start_time = time.perf_counter()
    
    try:
        log_event("flow_trace_semantic_operations", {
            "corr_id": corr_id,
            "step": "semantic_retriever_operations"
        })
        
        # Import semantic retriever
        sem_module = importlib.import_module("services.semantic_retriever")
        
        required_classes = ["SemanticRetriever", "TieredSemanticRetriever"]
        required_functions = ["search", "render_markdown"]
        
        missing_classes = [cls for cls in required_classes if not hasattr(sem_module, cls)]
        missing_functions = [func for func in required_functions if not hasattr(sem_module, func)]
        
        if missing_classes or missing_functions:
            raise RuntimeError(f"Missing semantic components - classes: {missing_classes}, functions: {missing_functions}")
        
        # Test basic search function
        search_func = getattr(sem_module, "search")
        search_sig = inspect.signature(search_func)
        
        # Test TieredSemanticRetriever instantiation
        TieredSemanticRetriever = getattr(sem_module, "TieredSemanticRetriever")
        
        try:
            test_retriever = TieredSemanticRetriever("global", score_threshold=0.25)
            retriever_methods = [method for method in dir(test_retriever) if not method.startswith("_")]
        except Exception as e:
            raise RuntimeError(f"Failed to create TieredSemanticRetriever: {e}")
        
        duration = (time.perf_counter() - start_time) * 1000
        
        return FlowStep(
            step_name="semantic_retriever_operations",
            status="success",
            duration_ms=duration,
            data={
                "module_path": str(sem_module.__file__),
                "available_classes": [cls for cls in required_classes if hasattr(sem_module, cls)],
                "available_functions": [func for func in required_functions if hasattr(sem_module, func)],
                "search_signature": str(search_sig),
                "retriever_methods": retriever_methods,
                "retriever_created": True
            }
        )
        
    except Exception as e:
        duration = (time.perf_counter() - start_time) * 1000
        log_event("flow_trace_semantic_operations_error", {
            "corr_id": corr_id,
            "error": str(e),
            "traceback": traceback.format_exc()
        })
        
        return FlowStep(
            step_name="semantic_retriever_operations",
            status="error",
            duration_ms=duration,
            error=str(e)
        )

async def trace_kb_service_interactions(query: str, corr_id: str) -> FlowStep:
    """Trace services/kb.py service interactions"""
    start_time = time.perf_counter()
    
    try:
        log_event("flow_trace_kb_interactions", {
            "corr_id": corr_id,
            "step": "kb_service_interactions"
        })
        
        # Import KB service
        kb_module = importlib.import_module("services.kb")
        
        # Check for key functions
        required_functions = ["search"]
        missing_functions = [func for func in required_functions if not hasattr(kb_module, func)]
        
        if missing_functions:
            raise RuntimeError(f"Missing KB functions: {missing_functions}")
        
        search_func = getattr(kb_module, "search")
        search_sig = inspect.signature(search_func)
        
        # Test search function parameters
        test_params = {"query": query, "k": 5}
        
        # Check if search function accepts our test parameters
        param_names = list(search_sig.parameters.keys())
        valid_params = {k: v for k, v in test_params.items() if k in param_names}
        
        duration = (time.perf_counter() - start_time) * 1000
        
        return FlowStep(
            step_name="kb_service_interactions",
            status="success",
            duration_ms=duration,
            data={
                "module_path": str(kb_module.__file__),
                "search_signature": str(search_sig),
                "search_parameters": param_names,
                "valid_test_params": list(valid_params.keys()),
                "search_callable": callable(search_func)
            }
        )
        
    except Exception as e:
        duration = (time.perf_counter() - start_time) * 1000
        log_event("flow_trace_kb_interactions_error", {
            "corr_id": corr_id,
            "error": str(e),
            "traceback": traceback.format_exc()
        })
        
        return FlowStep(
            step_name="kb_service_interactions",
            status="error",
            duration_ms=duration,
            error=str(e)
        )

async def trace_full_pipeline_integration(query: str, corr_id: str) -> FlowStep:
    """Trace full pipeline integration (ask → mcp → context → semantic → kb)"""
    start_time = time.perf_counter()
    
    try:
        log_event("flow_trace_full_integration", {
            "corr_id": corr_id,
            "step": "full_pipeline_integration"
        })
        
        # Import all components
        ctx_module = importlib.import_module("core.context_engine")
        sem_module = importlib.import_module("services.semantic_retriever")
        
        build_context = getattr(ctx_module, "build_context")
        ContextRequest = getattr(ctx_module, "ContextRequest")
        EngineConfig = getattr(ctx_module, "EngineConfig")
        RetrievalTier = getattr(ctx_module, "RetrievalTier")
        TierConfig = getattr(ctx_module, "TierConfig")
        TieredSemanticRetriever = getattr(sem_module, "TieredSemanticRetriever")
        
        # Build minimal configuration like the real pipeline
        score_thresh_env = os.getenv("RERANK_MIN_SCORE_GLOBAL") or os.getenv("SEMANTIC_SCORE_THRESHOLD")
        score_thresh = float(score_thresh_env) if score_thresh_env else 0.25
        
        retrievers = {
            RetrievalTier.GLOBAL: TieredSemanticRetriever("global", score_threshold=score_thresh),
            RetrievalTier.PROJECT_DOCS: TieredSemanticRetriever("project_docs", score_threshold=score_thresh),
        }
        
        config = EngineConfig(retrievers=retrievers)
        request = ContextRequest(query=query, corr_id=corr_id)
        
        # Test the actual build_context call (this is where it often fails)
        try:
            context_result = build_context(request, config)
            
            # Analyze the result
            result_type = type(context_result)
            has_context = hasattr(context_result, 'context') or (isinstance(context_result, dict) and 'context' in context_result)
            has_files = hasattr(context_result, 'files_used') or (isinstance(context_result, dict) and 'files_used' in context_result)
            
        except Exception as build_error:
            raise RuntimeError(f"build_context failed: {build_error}")
        
        duration = (time.perf_counter() - start_time) * 1000
        
        return FlowStep(
            step_name="full_pipeline_integration",
            status="success",
            duration_ms=duration,
            data={
                "score_threshold": score_thresh,
                "retrievers_created": len(retrievers),
                "context_result_type": str(result_type),
                "has_context_field": has_context,
                "has_files_field": has_files,
                "build_context_success": True,
                "integration_complete": True
            }
        )
        
    except Exception as e:
        duration = (time.perf_counter() - start_time) * 1000
        log_event("flow_trace_full_integration_error", {
            "corr_id": corr_id,
            "error": str(e),
            "traceback": traceback.format_exc()
        })
        
        return FlowStep(
            step_name="full_pipeline_integration",
            status="error",
            duration_ms=duration,
            error=str(e)
        )

# ──────────────────────────────────────────────────────────────────────────────
# Analysis and Recommendations
# ──────────────────────────────────────────────────────────────────────────────

def analyze_flow_trace(steps: List[FlowStep]) -> tuple[Optional[str], List[str]]:
    """Analyze flow trace results to identify break point and generate recommendations"""
    
    break_point = None
    recommendations = []
    
    # Find the first failure point
    for step in steps:
        if step.status == "error":
            break_point = step.step_name
            break
    
    # Generate specific recommendations based on failure patterns
    error_steps = [step for step in steps if step.status == "error"]
    
    if not error_steps:
        recommendations.append("✅ All pipeline steps completed successfully")
        recommendations.append("🔍 Check Railway deployment logs for runtime errors")
        recommendations.append("🌐 Test actual HTTP requests to deployed endpoints")
    else:
        for step in error_steps:
            step_name = step.step_name
            error_msg = step.error or ""
            
            if "import" in error_msg.lower():
                recommendations.append(f"🚫 Import Error in {step_name}: Check Python path and dependencies")
                recommendations.append("📦 Verify all required packages are installed in Railway environment")
                
            elif "attribute" in error_msg.lower():
                recommendations.append(f"🔧 Missing Attribute in {step_name}: Check for recent code changes")
                recommendations.append("🔄 Verify module exports and function signatures")
                
            elif "signature" in error_msg.lower() or "argument" in error_msg.lower():
                recommendations.append(f"⚙️ Function Signature Mismatch in {step_name}: Check parameter compatibility")
                recommendations.append("🔍 Review recent changes to function signatures")
                
            elif step_name == "context_engine_build":
                recommendations.append("🧠 Context Engine Issue: Check LlamaIndex configuration")
                recommendations.append("📊 Verify semantic retriever setup and index files")
                recommendations.append("🔧 Check environment variables: RERANK_MIN_SCORE_GLOBAL, TOPK_GLOBAL")
                
            elif step_name == "semantic_retriever_operations":
                recommendations.append("🔍 Semantic Retriever Issue: Check knowledge base connectivity")
                recommendations.append("📈 Verify embedding model configuration")
                recommendations.append("💾 Check index file availability and permissions")
                
            elif step_name == "kb_service_interactions":
                recommendations.append("💾 Knowledge Base Issue: Check database connectivity")
                recommendations.append("🔗 Verify KB service configuration and API keys")
    
    # Environment-specific recommendations
    recommendations.append("🚀 Railway Deployment Checks:")
    recommendations.append("  • Verify all environment variables are set correctly")
    recommendations.append("  • Check build logs for missing dependencies")
    recommendations.append("  • Ensure index files are included in deployment")
    recommendations.append("  • Verify service discovery between components")
    
    return break_point, recommendations

# ──────────────────────────────────────────────────────────────────────────────
# API Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/flow-trace", response_model=FlowTraceResponse)
async def run_flow_trace(
    request: FlowTraceRequest,
    http_request: Request,
    x_corr_id: Optional[str] = Header(default=None, alias="X-Corr-Id")
) -> FlowTraceResponse:
    """
    Run comprehensive flow tracing through the FastAPI + LlamaIndex pipeline.
    
    This endpoint traces the exact flow:
    ask.py → mcp_agent.run_mcp() → context_engine.build_context() → 
    semantic_retriever.search() → kb service interactions
    
    Returns detailed diagnostics to identify exactly where the pipeline breaks.
    """
    
    corr_id = x_corr_id or str(uuid4())
    start_time = time.perf_counter()
    
    log_event("flow_trace_start", {
        "corr_id": corr_id,
        "query": request.query,
        "deep_trace": request.enable_deep_trace,
        "test_mode": request.test_mode
    })
    
    steps: List[FlowStep] = []
    
    # Execute each tracing step
    trace_functions = [
        trace_ask_entry_point,
        trace_mcp_agent_invocation,
        trace_context_engine_build,
        trace_semantic_retriever_operations,
        trace_kb_service_interactions,
        trace_full_pipeline_integration
    ]
    
    for trace_func in trace_functions:
        try:
            step = await trace_func(request.query, corr_id)
            steps.append(step)
            
            # Stop on first error unless deep trace is enabled
            if step.status == "error" and not request.enable_deep_trace:
                break
                
        except Exception as e:
            # Create error step for any tracing function that fails
            error_step = FlowStep(
                step_name=trace_func.__name__,
                status="error",
                duration_ms=0.0,
                error=f"Trace function failed: {str(e)}"
            )
            steps.append(error_step)
            
            if not request.enable_deep_trace:
                break
    
    total_duration = (time.perf_counter() - start_time) * 1000
    
    # Analyze results
    break_point, recommendations = analyze_flow_trace(steps)
    
    success = all(step.status == "success" for step in steps)
    
    log_event("flow_trace_complete", {
        "corr_id": corr_id,
        "success": success,
        "break_point": break_point,
        "total_steps": len(steps),
        "total_duration_ms": total_duration
    })
    
    return FlowTraceResponse(
        success=success,
        corr_id=corr_id,
        total_duration_ms=total_duration,
        steps=steps,
        break_point=break_point,
        recommendations=recommendations
    )

# ──────────────────────────────────────────────────────────────────────────────
# Environment Configuration Check
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/env-config")
async def check_environment_config(
    x_corr_id: Optional[str] = Header(default=None, alias="X-Corr-Id")
) -> Dict[str, Any]:
    """Check critical environment variables and configuration"""
    
    corr_id = x_corr_id or str(uuid4())
    
    env_checks = {
        # Context Engine Config
        "RERANK_MIN_SCORE_GLOBAL": os.getenv("RERANK_MIN_SCORE_GLOBAL"),
        "SEMANTIC_SCORE_THRESHOLD": os.getenv("SEMANTIC_SCORE_THRESHOLD"),
        "TOPK_GLOBAL": os.getenv("TOPK_GLOBAL"),
        "TOPK_PROJECT_DOCS": os.getenv("TOPK_PROJECT_DOCS"),
        "MAX_CONTEXT_TOKENS": os.getenv("MAX_CONTEXT_TOKENS"),
        
        # Knowledge Base Config
        "KB_EMBED_MODEL": os.getenv("KB_EMBED_MODEL"),
        "INDEX_ROOT": os.getenv("INDEX_ROOT"),
        
        # API Keys
        "OPENAI_API_KEY": "SET" if os.getenv("OPENAI_API_KEY") else "MISSING",
        
        # System Config
        "ENV": os.getenv("ENV"),
        "MCP_SAFE_MODE": os.getenv("MCP_SAFE_MODE"),
        "ALLOW_KB_FALLBACK": os.getenv("ALLOW_KB_FALLBACK"),
    }
    
    # Check file system paths
    fs_checks = {}
    for path_name, path_env in [
        ("index_root", "INDEX_ROOT"),
        ("current_dir", None)
    ]:
        if path_env:
            path_value = os.getenv(path_env)
        else:
            path_value = str(Path.cwd())
            
        if path_value:
            path_obj = Path(path_value)
            fs_checks[path_name] = {
                "path": str(path_obj),
                "exists": path_obj.exists(),
                "is_dir": path_obj.is_dir() if path_obj.exists() else False,
                "readable": os.access(path_obj, os.R_OK) if path_obj.exists() else False
            }
    
    return {
        "corr_id": corr_id,
        "env_vars": env_checks,
        "filesystem": fs_checks,
        "python_path": os.getcwd(),
        "missing_critical_vars": [
            var for var, val in env_checks.items() 
            if val in [None, "MISSING"] and var in [
                "OPENAI_API_KEY", "KB_EMBED_MODEL", "INDEX_ROOT"
            ]
        ]
    }