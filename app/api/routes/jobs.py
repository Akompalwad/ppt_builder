from fastapi import APIRouter, Depends, HTTPException
from app.services.presentation_service import PresentationService
from app.api.routes.access import require_active_session
router=APIRouter(prefix="/api/jobs",tags=["jobs"]); service=PresentationService()
@router.get("/{job_id}")
def get_job(job_id:str, session_id: str = Depends(require_active_session)):
    job=service.job(job_id,session_id)
    if not job: raise HTTPException(404,"Job not found")
    return job
