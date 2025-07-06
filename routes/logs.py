# routes/logs.py

from fastapi import APIRouter, Query
from services.logs import get_recent_logs

router = APIRouter(prefix="/logs", tags=["logs"])

@router.get("/recent")
def recent_logs(n: int = 50, level_filter: str = None):
    logs = get_recent_logs(n=n, level_filter=level_filter)
    return {"logs": logs}
