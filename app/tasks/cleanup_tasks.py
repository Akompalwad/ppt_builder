from app.tasks.presentation_tasks import celery_app
from app.services.lifecycle_service import cleanup_expired_files

@celery_app.task
def cleanup_generated_files() -> list[str]:
    return cleanup_expired_files()
