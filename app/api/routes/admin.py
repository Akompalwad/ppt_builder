from fastapi import APIRouter, Depends, HTTPException

from app.api.routes.access import require_active_session
from app.services.admin_service import activity_snapshot, admin_user_for_session

router=APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/activity")
def admin_activity(session_id: str = Depends(require_active_session)):
    if not admin_user_for_session(session_id):
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    return activity_snapshot()
