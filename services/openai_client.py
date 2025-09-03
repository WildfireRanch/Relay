# File: services/openai_client.py
# Purpose: Thin async wrapper for OpenAI, returning {"text","usage","raw"}.
from __future__ import annotations
import os, asyncio, random
from typing import Any, Dict, Optional

try:
    from openai import AsyncOpenAI  # SDK 1.x
except Exception as e:
    AsyncOpenAI = None  # type: ignore

_TRANSIENT = ("timeout", "temporar", "rate limit", "unavailable", "again", "overloaded")

def _is_transient(ex: Exception) -> bool:
    return any(k in str(ex).lower() for k in _TRANSIENT)

def _jitter(n: int, base=0.25, cap=2.5) -> float:
    return min(cap, base * (2 ** n)) * random.random()

_client: Optional[Any] = None

def _client_or_raise():
    global _client
    if _client is None:
        if not AsyncOpenAI:
            raise RuntimeError("openai SDK not installed. pip install openai>=1.0.0")
        _client = AsyncOpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
            base_url=os.environ.get("OPENAI_BASE_URL") or None,  # supports Azure/Proxy
            max_retries=int(os.environ.get("OPENAI_MAX_RETRIES", "2")),  # SDK default ~2
        )
    return _client

async def chat_complete(
    *,
    system: str,
    user: str,
    model: str = "gpt-4o",
    timeout_s: int = 30,
) -> Dict[str, Any]:
    """
    Returns: {"text": <str>, "usage": {...} | None, "raw": <sdk object>}
    """
    cli = _client_or_raise()
    attempts = 0
    last_exc: Optional[Exception] = None

    while attempts < 3:
        attempts += 1
        try:
            # Route through the modern Responses API if available; fall back to Chat Completions
            async with asyncio.timeout(timeout_s):
                try:
                    # Preferred: Responses API (SDK 1.x)
                    resp = await cli.responses.create(
                        model=model,
                        instructions=system,
                        input=user,
                    )
                    text = getattr(resp, "output_text", None) or ""
                    usage = getattr(resp, "usage", None)
                    return {"text": text.strip(), "usage": usage, "raw": resp}
                except Exception:
                    # Back-compat: Chat Completions (still supported)
                    cc = await cli.chat.completions.create(
                        model=model,
                        messages=[{"role": "system", "content": system},
                                  {"role": "user", "content": user}],
                    )
                    text = (cc.choices[0].message.content or "") if cc.choices else ""
                    usage = getattr(cc, "usage", None)
                    return {"text": text.strip(), "usage": usage, "raw": cc}
        except asyncio.TimeoutError as ex:
            last_exc = ex
            if attempts >= 3: break
            await asyncio.sleep(_jitter(attempts))
        except Exception as ex:
            last_exc = ex
            if not _is_transient(ex) or attempts >= 3:
                break
            await asyncio.sleep(_jitter(attempts))

    # If we get here, we failed
    raise RuntimeError(f"OpenAI chat_complete failed after {attempts} attempts: {last_exc}")
