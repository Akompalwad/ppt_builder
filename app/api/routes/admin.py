from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.api.routes.access import require_active_session
from app.services.admin_service import activity_snapshot, admin_user_for_session, delete_feedback, login_history, purge_old_feedback
from app.models.database import FeedbackReport, SessionLocal
from app.services.lifecycle_service import cleanup_expired_files

router=APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/activity")
def admin_activity(session_id: str = Depends(require_active_session)):
    if not admin_user_for_session(session_id):
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    return activity_snapshot()


@router.get("/login-history")
def admin_login_history(session_id: str = Depends(require_active_session)):
    if not admin_user_for_session(session_id):
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    return {"events":login_history()}


@router.post("/cleanup-expired-files")
def cleanup_files(session_id: str = Depends(require_active_session)):
    if not admin_user_for_session(session_id):
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    removed=cleanup_expired_files()
    return {"removed":len(removed)}


@router.delete("/feedback/{feedback_id}")
def delete_feedback_report(feedback_id: str, session_id: str = Depends(require_active_session)):
    if not admin_user_for_session(session_id):
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    if not delete_feedback(feedback_id):
        raise HTTPException(status_code=404, detail="Feedback report not found")
    return {"deleted":True}


@router.post("/feedback/purge")
def purge_feedback(older_than_days: int = Query(30, ge=1, le=3650), session_id: str = Depends(require_active_session)):
    if not admin_user_for_session(session_id):
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    return {"removed":purge_old_feedback(older_than_days)}


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
