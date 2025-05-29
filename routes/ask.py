import os
from fastapi import APIRouter, Depends, Header, HTTPException
from services import agent

router = APIRouter(prefix="/ask", tags=["ask"])


def auth(x_api_key: str = Header(..., alias="X-API-Key")):
    """Simple header check against the API_KEY env var."""
    if x_api_key != os.getenv("API_KEY"):
        raise HTTPException(status_code=401, detail="bad key")


@router.get("")  # ← no slash keeps canonical path at /ask
async def ask(q: str, user=Depends(auth)):
    """Return an answer from the Echo agent."""
    answer_text: str = await agent.answer(q)
    return {"answer": answer_text}
