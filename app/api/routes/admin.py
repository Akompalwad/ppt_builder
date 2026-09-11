from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.routes.access import require_active_session
from app.services.admin_service import activity_snapshot, admin_user_for_session
from app.models.database import FeedbackReport, SessionLocal

router=APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/activity")
def admin_activity(session_id: str = Depends(require_active_session)):
    if not admin_user_for_session(session_id):
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    return activity_snapshot()


@router.get("/feedback/{feedback_id}/screenshot")
def feedback_screenshot(feedback_id: str, session_id: str = Depends(require_active_session)):
    if not admin_user_for_session(session_id):
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    with SessionLocal() as db:
        report=db.get(FeedbackReport, feedback_id)
        screenshot=Path(report.screenshot_path) if report and report.screenshot_path else None
    if not screenshot or not screenshot.is_file():
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(screenshot)
