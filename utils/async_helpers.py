# ──────────────────────────────────────────────────────────────────────────────
# File: utils/async_helpers.py
# Purpose: Centralized async/sync compatibility utilities for Relay pipeline
#
# Why this exists:
#   • Multiple _maybe_await implementations were scattered across routes/
#   • Function signature inconsistencies causing async/sync call failures
#   • Single source of truth for async/sync compatibility patterns
# ──────────────────────────────────────────────────────────────────────────────

import asyncio
import inspect
from inspect import iscoroutinefunction
from typing import Any, Callable, Optional


async def maybe_await(func: Callable, *args, timeout_s: float = 45, **kwargs) -> Any:
    """
    Universal async/sync function caller with timeout support.

    Handles both coroutine functions (async def) and regular functions,
    executing them appropriately with configurable timeout.

    Args:
        func: Function to call (sync or async)
        *args: Positional arguments to pass to func
        timeout_s: Timeout in seconds (default 45s)
        **kwargs: Keyword arguments to pass to func

    Returns:
        Result of function execution

    Raises:
        asyncio.TimeoutError: If execution exceeds timeout_s
        TypeError: If positional args are passed to keyword-only function
        Any exception raised by the function itself
    """
    # Check for keyword-only parameter violations
    if args:
        try:
            sig = inspect.signature(func)
            # Check if function has keyword-only parameters and we're passing positional args
            has_keyword_only = any(
                param.kind == param.KEYWORD_ONLY
                for param in sig.parameters.values()
            )

            if has_keyword_only:
                # Count non-keyword-only parameters that can accept positional args
                positional_params = [
                    param for param in sig.parameters.values()
                    if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD)
                ]

                # If we have more positional args than can be accepted, raise error
                if len(args) > len(positional_params):
                    raise TypeError(
                        f"Function {func.__name__} has keyword-only parameters but "
                        f"received {len(args)} positional arguments. "
                        f"Only {len(positional_params)} positional arguments are allowed."
                    )
        except (ValueError, TypeError):
            # If we can't inspect the signature, proceed with the call
            # The function itself will raise appropriate errors
            pass

    if iscoroutinefunction(func):
        # Async function - await with timeout
        return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_s)
    else:
        # Sync function - run in executor with timeout
        loop = asyncio.get_running_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, lambda: func(*args, **kwargs)),
            timeout=timeout_s
        )


async def maybe_await_simple(x: Any) -> Any:
    """
    Simple awaiter for values that may or may not be awaitable.

    Used for retriever results and other objects that might be coroutines.

    Args:
        x: Value that may or may not be awaitable

    Returns:
        Awaited result if x is awaitable, otherwise x unchanged
    """
    return await x if inspect.isawaitable(x) else x


async def try_call(fn: Callable, *args, **kwargs) -> Optional[Any]:
    """
    Safe function caller that returns None on any exception.

    Useful for optional operations that shouldn't crash the pipeline.

    Args:
        fn: Function to call
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        Function result or None if exception occurred
    """
    try:
        result = fn(*args, **kwargs)
        return await maybe_await_simple(result)
    except Exception:
        return None


def filter_kwargs_for_callable(func: Callable, **kwargs) -> dict:
    """
    Filter kwargs to only include parameters that the function accepts.

    Prevents TypeError when calling functions with unexpected kwargs.

    Args:
        func: Function to inspect
        **kwargs: All available keyword arguments

    Returns:
        Dictionary containing only kwargs that func accepts
    """
    try:
        sig = inspect.signature(func)
        params = set(sig.parameters.keys())

        # Include **kwargs if function has var-keyword parameter
        has_var_keyword = any(
            p.kind == p.VAR_KEYWORD for p in sig.parameters.values()
        )

        if has_var_keyword:
            return kwargs
        else:
            return {k: v for k, v in kwargs.items() if k in params}
    except Exception:
        # Fallback: return all kwargs if inspection fails
        return kwargs