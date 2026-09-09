from __future__ import annotations
from pathlib import Path
from sqlalchemy import select
from app.models.database import GenerationJob, Presentation, PresentationVersion, SessionLocal, User
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
        # Google OAuth is intentionally disabled during testing. Isolate data
        # by the claimed browser session until a real identity provider is on.
        email=f"session-{session_id}@local.deckforge" if session_id != "development" else DEV_EMAIL
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
            return [
                {"id":p.id,"title":p.title,"status":p.status,"created_at":p.created_at.isoformat(),"updated_at":p.updated_at.isoformat()}
                for p in presentations
            ]
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
                    asset_results=ImageService().attach_assets(spec,get_settings().local_storage_path / presentation_id / "assets",request.include_external_images)
                    # Image attachment changes the selected PPTX composition.
                    # Re-run layout QA now that image-backed slides have their
                    # final, narrower text area.
                    PresentationQAAgent().validate_and_recompose(spec)
                    spec.metadata["asset_generation"]=asset_results
                    spec.metadata["file_expires_at"]=schedule_expiry(presentation_id)
                    version=PresentationVersion(presentation_id=presentation_id,version_number=1,spec_json=spec.model_dump(mode="json"),generated_by="pipeline"); db.add(version); db.flush()
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
            return None if not j or not presentation or presentation.user_id != user.id else {"id":j.id,"presentation_id":j.presentation_id,"status":j.status,"progress":j.progress,"current_stage":j.current_stage,"error_message":j.error_message}
    def edit(self,presentation_id:str,slide_number:int,instruction:str,session_id: str):
        with SessionLocal() as db:
            p=db.get(Presentation,presentation_id); user=self._user(db,session_id)
            if not p or p.user_id != user.id: raise LookupError("Presentation not found")
            current=db.get(PresentationVersion,p.current_version_id); spec=PresentationSpec.model_validate(current.spec_json); updated=PresentationOrchestrator().edit_slide(spec,slide_number,instruction)
            # Edits can be model-generated too; apply the same text-fit pass
            # used by new decks before writing a fresh PPTX version.
            PresentationQAAgent().validate_and_recompose(updated)
            number=db.scalar(select(PresentationVersion.version_number).where(PresentationVersion.presentation_id==presentation_id).order_by(PresentationVersion.version_number.desc()))+1
            updated.metadata["file_expires_at"]=schedule_expiry(presentation_id)
            version=PresentationVersion(presentation_id=presentation_id,version_number=number,spec_json=updated.model_dump(mode="json"),generated_by="slide_edit"); db.add(version); db.flush(); p.current_version_id=version.id; p.status="COMPLETED"; file=get_settings().local_storage_path/presentation_id/"versions"/str(number)/"presentation.pptx"; build_presentation(updated,file); db.commit(); return updated,number
