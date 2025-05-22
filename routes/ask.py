from fastapi import APIRouter, Query
from services.agent import ask_agent

router = APIRouter()

@router.get("/ask")
def ask_gpt(prompt: str = Query(...)):
    reply = ask_agent(prompt)
    return {"response": reply}


