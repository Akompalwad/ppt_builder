"""Celery entry point for production workers.

The API currently uses FastAPI BackgroundTasks for zero-dependency local mode;
configure this task as the dispatch target when Redis/Celery is enabled.
"""
from celery import Celery
from app.config import get_settings
from app.schemas.presentation import CreatePresentationRequest
from app.services.presentation_service import PresentationService

celery_app = Celery("deckforge", broker=get_settings().redis_url, backend=get_settings().redis_url)
celery_app.conf.beat_schedule = {"cleanup-expired-files": {"task":"app.tasks.cleanup_tasks.cleanup_generated_files", "schedule":600}}

@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=2)
def generate_presentation(self, presentation_id: str, job_id: str, request: dict):
    PresentationService().generate(presentation_id, job_id, CreatePresentationRequest.model_validate(request))
