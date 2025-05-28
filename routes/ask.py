from fastapi import APIRouter, Depends, Header, HTTPException
from services import agent

router = APIRouter(prefix="/ask", tags=["ask"])

def auth(key: str = Header(..., alias="X-API-Key")):
    if key != os.getenv("API_KEY"):
        raise HTTPException(401, "bad key")

@router.get("/")
async def ask(q: str, user=Depends(auth)):
    answer_text = await agent.answer(q)
    return {"answer": answer_text}
