from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import re
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
    # These are whole-pipeline budgets rather than a timeout for one API call.
    # They deliberately include the renderer and image-aware QA passes that
    # happen after the content model has returned.
    _PIPELINE_STAGES=(
        ("brief", 30), ("theme", 30), ("content", 90), ("story", 30),
        ("visuals", 55), ("qa", 50), ("export", 15),
    )

    @staticmethod
    def _pipeline_total_budget(slide_count: int) -> int:
        """One monotonic ETA baseline for a new deck generation job."""
        # Active content call (90s), post-content agents (150s), and every
        # later slide request (80s). A 10-slide deck starts at 16 minutes;
        # around slide 7 it naturally lands near eight minutes.
        return 240 + max(0, slide_count-1)*80

    @staticmethod
    def _stage_budget(stage: str) -> int:
        """Conservative stage budgets, used for an explicitly labelled ETA."""
        stage=stage.lower()
        return (
            90 if "slide content" in stage or "drafting" in stage else
            30 if any(token in stage for token in ("brief", "theme", "storyline", "design director")) else
            25 if any(token in stage for token in ("visual asset", "image", "qa", "quality")) else
            15 if any(token in stage for token in ("renderer", "pptx", "composing")) else 45
        )

    @classmethod
    def _pipeline_remaining_budget(cls, stage: str) -> int:
        """Return the downstream budget for the current stage plus all agents.

        The stage strings are intentionally human-readable, so this maps them
        back to the same seven groups shown in the UI. A content agent drafting
        slide 3/10 reserves time for its remaining slide calls as well.
        """
        lower=stage.lower()
        if "brief" in lower or "classification" in lower:
            index=0
        elif "theme" in lower:
            index=1
        elif "slide content" in lower or "drafting" in lower or "content validation" in lower:
            index=2
        elif "storyline" in lower or "story" in lower:
            index=3
        elif any(token in lower for token in ("design director", "visual asset", "image")):
            index=4
        elif any(token in lower for token in ("qa", "quality")):
            index=5
        elif any(token in lower for token in ("renderer", "pptx", "composer", "composing")):
            index=6
        else:
            index=2
        remaining=sum(seconds for _, seconds in cls._PIPELINE_STAGES[index:])
        slide_match=re.search(r"slide\s+(\d+)\s*/\s*(\d+)", lower)
        if index == 2 and slide_match:
            current, total=(int(value) for value in slide_match.groups())
            # Each later slide is a separate cloud request. A 10-slide deck
            # at slide 7 therefore still reserves roughly eight minutes when
            # the active slide, three remaining calls, visuals, QA, and PPTX
            # export are all included—not merely the active call's timeout.
            remaining+=max(0, total-current)*80
        return remaining

    @staticmethod
    def _timing_estimate(job: GenerationJob, *, jobs_ahead: int = 0) -> dict:
        """Return an honest, coarse ETA without pretending cloud work is deterministic.

        Provider latency, image retrieval, and shared rate gates vary by job.
        The estimate combines elapsed time, progress, and a conservative
        baseline for the active stage, and is deliberately labelled as an
        estimate by the UI.
        """
        created=job.created_at.replace(tzinfo=timezone.utc) if job.created_at.tzinfo is None else job.created_at
        elapsed=max(0, int((datetime.now(timezone.utc)-created).total_seconds()))
        status=str(job.status or "").upper()
        if status == "COMPLETED":
            return {"elapsed_seconds":elapsed, "estimated_remaining_seconds":0, "current_stage_eta_seconds":0, "is_estimate":True}
        stage=str(job.current_stage or "")
        stage_budget=PresentationService._stage_budget(stage)
        stage_started=job.stage_started_at or job.created_at
        stage_started=stage_started.replace(tzinfo=timezone.utc) if stage_started.tzinfo is None else stage_started
        stage_elapsed=max(0, int((datetime.now(timezone.utc)-stage_started).total_seconds()))
        stage_remaining=max(0, stage_budget-stage_elapsed)
        pipeline_budget=PresentationService._pipeline_remaining_budget(stage)
        total_budget=job.estimated_total_seconds or pipeline_budget
        if status == "QUEUED":
            # A queued deck waits for its own typical run plus every job in
            # front of it. This is intentionally a range-like estimate rather
            # than a false promise of an exact start time.
            remaining=min(1800, max(total_budget, (jobs_ahead + 1) * total_budget))
            return {"elapsed_seconds":elapsed, "estimated_remaining_seconds":remaining, "current_stage_eta_seconds":stage_budget, "current_stage_elapsed_seconds":stage_elapsed, "is_estimate":True}
        # Do not re-estimate upwards when the content stage begins. This is a
        # real countdown from the budget set at job creation. The stage-aware
        # floor protects older jobs created before the baseline was persisted.
        baseline_remaining=max(0, total_budget-elapsed)
        stage_aware_remaining=stage_remaining + max(0, pipeline_budget-stage_budget)
        remaining=min(1800, baseline_remaining if job.estimated_total_seconds else max(baseline_remaining, stage_aware_remaining))
        return {"elapsed_seconds":elapsed, "estimated_remaining_seconds":remaining, "current_stage_eta_seconds":stage_remaining, "current_stage_elapsed_seconds":stage_elapsed, "is_estimate":True}

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
            user=self._user(db,session_id); p=Presentation(user_id=user.id,title=request.topic[:500],topic=request.topic); db.add(p); db.flush(); job=GenerationJob(presentation_id=p.id,estimated_total_seconds=self._pipeline_total_budget(request.slide_count)); db.add(job); db.commit(); return p.id,job.id
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
                def progress(stage,value): job.current_stage=stage; job.progress=value; job.status="RUNNING"; job.stage_started_at=datetime.utcnow(); db.commit()
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
            result={"id":j.id,"presentation_id":j.presentation_id,"status":j.status,"progress":j.progress,"current_stage":j.current_stage,"error_message":j.error_message,"created_at":j.created_at.isoformat(),"stage_started_at":j.stage_started_at.isoformat() if j.stage_started_at else None}
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
                result["timing"]=self._timing_estimate(j, jobs_ahead=queue_state["jobs_ahead"])
            else:
                result["timing"]=self._timing_estimate(j)
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
                    job.current_stage=stage; job.progress=value; job.status="RUNNING"; job.stage_started_at=datetime.utcnow(); db.commit()
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
