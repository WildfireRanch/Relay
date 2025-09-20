"""Poem mirror using X API (ranch_wildfire timeline)."""

import os
from typing import Any, Dict, List

import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/poems", tags=["poems"])

X_BEARER = os.environ.get("X_BEARER")
USER = os.environ.get("X_USERNAME", "ranch_wildfire")
BASE = "https://api.x.com/2"

if not X_BEARER:
    # Fail fast so misconfigurations show up during startup.
    raise RuntimeError("Missing X_BEARER environment variable")


async def _fetch_json(client: httpx.AsyncClient, url: str, *, params: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    response = await client.get(url, params=params, headers=headers)
    if response.status_code != 200:
        raise HTTPException(response.status_code, response.text)
    return response.json()


@router.get("/latest")
async def poems_latest() -> List[Dict[str, Any]]:
    headers = {"Authorization": f"Bearer {X_BEARER}"}
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            user_payload = await _fetch_json(
                http,
                f"{BASE}/users/by",
                params={"usernames": USER},
                headers=headers,
            )
            data = user_payload.get("data") or []
            if not data:
                raise HTTPException(404, "user not found")
            uid = data[0]["id"]

            tweets_payload = await _fetch_json(
                http,
                f"{BASE}/users/{uid}/tweets",
                params={"max_results": 5, "tweet.fields": "created_at"},
                headers=headers,
            )
            tweets = tweets_payload.get("data", [])
            return [
                {
                    "id": tweet["id"],
                    "text": tweet["text"],
                    "created_at": tweet.get("created_at"),
                }
                for tweet in tweets
            ]
    except httpx.RequestError as exc:
        raise HTTPException(502, f"upstream error: {exc}") from exc
