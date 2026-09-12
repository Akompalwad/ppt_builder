from __future__ import annotations
from pathlib import Path
from sqlalchemy import select
from app.models.database import GenerationJob, OAuthSession, Presentation, PresentationVersion, SessionLocal, User
from app.schemas.presentation import CreatePresentationRequest, PresentationSpec
from app.agents.orchestrator import PresentationOrchestrator
from app.agents.qa_agent import PresentationQAAgent
from app.rendering.pptx_builder import build_presentation
from app.config import get_settings
from app.services.image_service import ImageService
from app.services.lifecycle_service import schedule_expiry
from app.services.generation_queue import shared_generation_queue

DEV_EMAIL="local@example.test"
class PresentationService:
    def _user(self, db, session_id: str):
        oauth_session=db.get(OAuthSession, session_id)
        if oauth_session:
            user=db.get(User, oauth_session.user_id)
            if user:
                return user
        # In development mode, isolate data by browser session until a real
        # identity provider is enabled.
        email=f"session-{session_id}@local.slideweaver" if session_id != "development" else DEV_EMAIL
        user=db.scalar(select(User).where(User.email==email))
        if not user: user=User(email=email,display_name="Testing User",provider="session"); db.add(user); db.flush()
        return user
    def create(self, request: CreatePresentationRequest, session_id: str) -> tuple[str,str]:
        with SessionLocal() as db:
            user=self._user(db,session_id); p=Presentation(user_id=user.id,title=request.topic[:500],topic=request.topic); db.add(p); db.flush(); job=GenerationJob(presentation_id=p.id); db.add(job); db.commit(); return p.id,job.id
    def list_for_current_user(self, session_id: str) -> list[dict]:
        """History for the active profile; Google auth will supply real users later."""
        with SessionLocal() as db:
            user=self._user(db,session_id)
            presentations=db.scalars(
                select(Presentation).where(Presentation.user_id==user.id).order_by(Presentation.updated_at.desc())
            ).all()
            history=[]
            for presentation in presentations:
                version=db.get(PresentationVersion,presentation.current_version_id) if presentation.current_version_id else None
                spec_json=version.spec_json or {} if version else {}
                metadata=spec_json.get("metadata", {})
                slides=spec_json.get("slides", [])
                design=spec_json.get("design_system", {})
                history.append({
                    "id":presentation.id,
                    "title":presentation.title,
                    "status":presentation.status,
                    "created_at":presentation.created_at.isoformat(),
                    "updated_at":presentation.updated_at.isoformat(),
                    "file_expires_at":metadata.get("file_expires_at"),
                    "slide_count":len(slides),
                    "theme":spec_json.get("theme"),
                    "accent_color":design.get("primary_color"),
                })
            return history
    def active_job_for_current_user(self, session_id: str) -> dict | None:
        """Return the newest unfinished generation job for the signed-in user."""
        with SessionLocal() as db:
            user=self._user(db,session_id)
            job=db.scalar(
                select(GenerationJob)
                .join(Presentation, GenerationJob.presentation_id == Presentation.id)
                .where(
                    Presentation.user_id == user.id,
                    GenerationJob.status.in_(("QUEUED", "RUNNING")),
                    GenerationJob.job_type == "generate",
                )
                .order_by(GenerationJob.created_at.desc())
            )
            job_id=job.id if job else None
        return self.job(job_id, session_id) if job_id else None
    def generate(self,presentation_id:str,job_id:str,request:CreatePresentationRequest):
        # The job remains QUEUED in the database until it receives its fair
        # slot. This prevents multiple users from exhausting one shared model
        # quota by interleaving the slides of several decks.
        queue=shared_generation_queue(get_settings().generation_max_concurrent_jobs)
        with queue.slot(job_id):
            with SessionLocal() as db:
                job=db.get(GenerationJob,job_id); presentation=db.get(Presentation,presentation_id)
                def progress(stage,value): job.current_stage=stage; job.progress=value; job.status="RUNNING"; db.commit()
                try:
                    spec=PresentationOrchestrator().generate(request,progress)
                    progress("Visual Asset Service — retrieving topic-specific imagery", 94)
                    asset_results=ImageService().attach_assets(spec,get_settings().local_storage_path / presentation_id / "assets",request.include_external_images)
                    # Image attachment changes the selected PPTX composition.
                    # Re-run layout QA now that image-backed slides have their
                    # final, narrower text area.
                    progress("Presentation QA Agent — rechecking image-aware layouts", 96)
                    PresentationQAAgent().validate_and_recompose(spec)
                    spec.metadata["asset_generation"]=asset_results
                    spec.metadata["file_expires_at"]=schedule_expiry(presentation_id)
                    version=PresentationVersion(presentation_id=presentation_id,version_number=1,spec_json=spec.model_dump(mode="json"),generated_by="pipeline"); db.add(version); db.flush()
                    progress("PPTX Renderer — building the editable presentation", 98)
                    file=get_settings().local_storage_path / presentation_id / "versions" / "1" / "presentation.pptx"; build_presentation(spec,file)
                    presentation.title=spec.title; presentation.status="COMPLETED"; presentation.current_version_id=version.id; job.status="COMPLETED"; job.progress=100; job.current_stage="COMPLETED"; db.commit()
                except Exception as exc:
                    presentation.status="FAILED"; job.status="FAILED"; job.error_message="Generation could not be completed."; db.commit(); raise exc
    def get(self,presentation_id:str,session_id: str):
        with SessionLocal() as db:
            p=db.get(Presentation,presentation_id)
            user=self._user(db,session_id)
            if not p or p.user_id != user.id: return None
            v=db.get(PresentationVersion,p.current_version_id) if p.current_version_id else None
            return {"id":p.id,"title":p.title,"topic":p.topic,"status":p.status,"current_version_id":p.current_version_id,"spec":v.spec_json if v else None}
    def job(self,job_id:str,session_id: str):
        with SessionLocal() as db:
            j=db.get(GenerationJob,job_id); user=self._user(db,session_id); presentation=db.get(Presentation,j.presentation_id) if j else None
            if not j or not presentation or presentation.user_id != user.id:
                return None
            result={"id":j.id,"presentation_id":j.presentation_id,"status":j.status,"progress":j.progress,"current_stage":j.current_stage,"error_message":j.error_message}
            if j.status in {"QUEUED","RUNNING"}:
                queue=shared_generation_queue(get_settings().generation_max_concurrent_jobs)
                # The database covers the brief interval after the API accepts
                # a job but before FastAPI starts its background task, while
                # the queue still supplies the configured concurrency detail.
                active_jobs=db.scalars(
                    select(GenerationJob)
                    .where(GenerationJob.status.in_(("QUEUED","RUNNING")))
                    .order_by(GenerationJob.created_at,GenerationJob.id)
                ).all()
                position=next((index for index, queued in enumerate(active_jobs, start=1) if queued.id==j.id),None)
                queue_state=queue.snapshot(j.id)
                queue_state.update({
                    "queue_depth":len(active_jobs),
                    "waiting_jobs":sum(queued.status=="QUEUED" for queued in active_jobs),
                    "active_jobs":sum(queued.status=="RUNNING" for queued in active_jobs),
                    "position":position,
                    "jobs_ahead":max(0,(position or 1)-1),
                })
                result["queue"]=queue_state
            return result
    def create_slide_edit(self,presentation_id:str,slide_number:int,instruction:str,session_id:str) -> str:
        """Queue an isolated edit without making the existing deck unavailable."""
        with SessionLocal() as db:
            presentation=db.get(Presentation,presentation_id); user=self._user(db,session_id)
            if not presentation or presentation.user_id != user.id or not presentation.current_version_id:
                raise LookupError("Presentation not found")
            current=db.get(PresentationVersion,presentation.current_version_id)
            if not current or not 1 <= slide_number <= len(PresentationSpec.model_validate(current.spec_json).slides):
                raise IndexError("Slide not found")
            job=GenerationJob(
                presentation_id=presentation_id,
                job_type="slide_edit",
                current_stage=f"Slide {slide_number} edit queued",
            )
            db.add(job); db.commit()
            return job.id

    def generate_slide_edit(self,presentation_id:str,job_id:str,slide_number:int,instruction:str):
        """Run one slide through content, QA, and PPTX stages as a tracked job."""
        queue=shared_generation_queue(get_settings().generation_max_concurrent_jobs)
        with queue.slot(job_id):
            with SessionLocal() as db:
                job=db.get(GenerationJob,job_id); presentation=db.get(Presentation,presentation_id)
                if not job or not presentation:
                    return
                def progress(stage:str,value:int):
                    job.current_stage=stage; job.progress=value; job.status="RUNNING"; db.commit()
                try:
                    current=db.get(PresentationVersion,presentation.current_version_id)
                    spec=PresentationSpec.model_validate(current.spec_json)
                    progress(f"Slide Content Agent — rewriting slide {slide_number}",28)
                    updated=PresentationOrchestrator().edit_slide(spec,slide_number,instruction)
                    if updated.slides[slide_number-1].visual_spec.get("edit_image_requested"):
                        progress("Visual Asset Agent — adding requested image",52)
                        asset_result=ImageService().attach_slide_asset(
                            updated, slide_number, get_settings().local_storage_path / presentation_id / "assets"
                        )
                        updated.metadata["last_slide_edit_image"]=asset_result
                        if asset_result["status"] != "generated":
                            updated.slides[slide_number-1].visual_spec.pop("edit_image_requested",None)
                    progress("Presentation QA Agent — checking edited slide",68)
                    PresentationQAAgent().validate_and_recompose(updated)
                    number=(db.scalar(select(PresentationVersion.version_number).where(PresentationVersion.presentation_id==presentation_id).order_by(PresentationVersion.version_number.desc())) or 0)+1
                    updated.metadata["file_expires_at"]=schedule_expiry(presentation_id)
                    updated.metadata["last_slide_edit"]={"slide_number":slide_number,"version_number":number,"status":"completed"}
                    version=PresentationVersion(presentation_id=presentation_id,version_number=number,spec_json=updated.model_dump(mode="json"),generated_by="slide_edit")
                    db.add(version); db.flush(); presentation.current_version_id=version.id
                    progress("PPTX Renderer — rebuilding editable presentation",90)
                    file=get_settings().local_storage_path/presentation_id/"versions"/str(number)/"presentation.pptx"
                    build_presentation(updated,file)
                    job.status="COMPLETED"; job.progress=100; job.current_stage=f"Slide {slide_number} updated"; db.commit()
                except Exception:
                    job.status="FAILED"; job.error_message="The slide adjustment could not be applied."; db.commit()
                    raise

    def edit(self,presentation_id:str,slide_number:int,instruction:str,session_id: str):
        with SessionLocal() as db:
            p=db.get(Presentation,presentation_id); user=self._user(db,session_id)
            if not p or p.user_id != user.id: raise LookupError("Presentation not found")
            current=db.get(PresentationVersion,p.current_version_id); spec=PresentationSpec.model_validate(current.spec_json); updated=PresentationOrchestrator().edit_slide(spec,slide_number,instruction)
            if updated.slides[slide_number-1].visual_spec.get("edit_image_requested"):
                asset_result=ImageService().attach_slide_asset(
                    updated, slide_number, get_settings().local_storage_path / presentation_id / "assets"
                )
                updated.metadata["last_slide_edit_image"]=asset_result
                if asset_result["status"] != "generated":
                    updated.slides[slide_number-1].visual_spec.pop("edit_image_requested",None)
            # Edits can be model-generated too; apply the same text-fit pass
            # used by new decks before writing a fresh PPTX version.
            PresentationQAAgent().validate_and_recompose(updated)
            number=db.scalar(select(PresentationVersion.version_number).where(PresentationVersion.presentation_id==presentation_id).order_by(PresentationVersion.version_number.desc()))+1
            updated.metadata["file_expires_at"]=schedule_expiry(presentation_id)
            version=PresentationVersion(presentation_id=presentation_id,version_number=number,spec_json=updated.model_dump(mode="json"),generated_by="slide_edit"); db.add(version); db.flush(); p.current_version_id=version.id; p.status="COMPLETED"; file=get_settings().local_storage_path/presentation_id/"versions"/str(number)/"presentation.pptx"; build_presentation(updated,file); db.commit(); return updated,number
