from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from app.schemas.presentation import CreatePresentationRequest
from app.services.presentation_service import PresentationService
from app.config import get_settings
from app.api.routes.access import require_active_session
router=APIRouter(prefix="/api/presentations",tags=["presentations"]); service=PresentationService()
@router.get("")
@router.get("/")
def list_presentations(session_id: str = Depends(require_active_session)):
    return service.list_for_current_user(session_id)
@router.post("")
def create(request:CreatePresentationRequest, tasks:BackgroundTasks, session_id: str = Depends(require_active_session)):
    presentation_id,job_id=service.create(request,session_id); tasks.add_task(service.generate,presentation_id,job_id,request); return {"presentation_id":presentation_id,"job_id":job_id}
@router.get("/{presentation_id}")
def get(presentation_id:str, session_id: str = Depends(require_active_session)):
    result=service.get(presentation_id,session_id)
    if not result: raise HTTPException(404,"Presentation not found")
    return result
@router.get("/{presentation_id}/status")
def status(presentation_id:str, session_id: str = Depends(require_active_session)):
    result=service.get(presentation_id,session_id)
    if not result: raise HTTPException(404,"Presentation not found")
    return {k:result[k] for k in ("id","status","current_version_id")}
@router.post("/{presentation_id}/slides/{slide_number}/edit")
def edit(presentation_id:str,slide_number:int,instruction:str,tasks:BackgroundTasks, session_id: str = Depends(require_active_session)):
    try:
        job_id=service.create_slide_edit(presentation_id,slide_number,instruction,session_id)
        tasks.add_task(service.generate_slide_edit,presentation_id,job_id,slide_number,instruction)
        return {"job_id":job_id,"presentation_id":presentation_id,"slide_number":slide_number,"status":"QUEUED"}
    except (AttributeError,IndexError,LookupError): raise HTTPException(404,"Presentation or slide not found")
@router.get("/{presentation_id}/download")
def download(presentation_id:str, session_id: str = Depends(require_active_session)):
    result=service.get(presentation_id,session_id)
    if not result or not result["current_version_id"]: raise HTTPException(404,"Presentation not ready")
    from app.models.database import PresentationVersion, SessionLocal
    with SessionLocal() as db: v=db.get(PresentationVersion,result["current_version_id"]); path=get_settings().local_storage_path/presentation_id/"versions"/str(v.version_number)/"presentation.pptx"
    if not path.exists(): raise HTTPException(status_code=410, detail="This generated file has expired. Edit or regenerate the presentation to create a new file.")
    return FileResponse(path,filename=f"{result['title'][:80]}.pptx")
