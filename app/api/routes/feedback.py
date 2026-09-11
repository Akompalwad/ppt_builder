"""Private, server-side collection of user feedback and reproducible errors."""
from __future__ import annotations

import base64
import binascii
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.api.routes.access import require_active_session
from app.config import get_settings
from app.models.database import FeedbackReport, SessionLocal
from app.schemas.presentation import FeedbackRequest

router=APIRouter(prefix="/api/feedback", tags=["feedback"])
MAX_SCREENSHOT_BYTES=3 * 1024 * 1024


@router.post("")
def submit_feedback(request: FeedbackRequest, session_id: str = Depends(require_active_session)):
    screenshot_path=None
    report_id=FeedbackReport().id
    if request.screenshot_base64:
        if not request.screenshot_name or not request.screenshot_mime_type:
            raise HTTPException(status_code=400, detail="Screenshot metadata is incomplete.")
        try:
            image=base64.b64decode(request.screenshot_base64, validate=True)
        except (ValueError, binascii.Error):
            raise HTTPException(status_code=400, detail="Screenshot data is invalid.")
        if not image or len(image) > MAX_SCREENSHOT_BYTES:
            raise HTTPException(status_code=413, detail="Screenshots must be smaller than 3 MB.")
        suffix=".png" if request.screenshot_mime_type == "image/png" else ".jpg"
        path: Path=get_settings().feedback_storage_path / f"{report_id}{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(image)
        screenshot_path=str(path)
    report=FeedbackReport(
        id=report_id, session_id=session_id, category=request.category,
        message=request.message.strip(), prompt=request.prompt.strip() if request.prompt else None,
        error_details=request.error_details.strip() if request.error_details else None,
        reply_to=request.reply_to.strip() if request.reply_to else None,
        screenshot_path=screenshot_path,
    )
    with SessionLocal() as db:
        db.add(report)
        db.commit()
    return {"id": report.id, "status": "received"}
