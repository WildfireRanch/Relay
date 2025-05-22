from fastapi import APIRouter, Query

router = APIRouter()

@router.post("/control")
def control_action(action: str = Query(...)):
    return {"message": f"Action received: {action}"}
