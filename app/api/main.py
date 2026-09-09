import asyncio
import logging
from contextlib import suppress
from fastapi import FastAPI
from app.models.database import init_db
from app.api.routes import access,health,presentations,jobs,llm
from app.config import get_settings
from app.services.lifecycle_service import cleanup_expired_files
app=FastAPI(title="SlideWeaver API",version="0.1.0")
cleanup_task: asyncio.Task | None = None
logger=logging.getLogger(__name__)

async def cleanup_loop():
    while True:
        try:
            # Run once immediately at API startup, then at the configured
            # interval. This removes files left behind while the API was down.
            removed=await asyncio.to_thread(cleanup_expired_files)
            if removed:
                logger.info("Removed %d expired presentation storage directories", len(removed))
        except Exception:
            # Retention must not silently stop forever because one malformed
            # directory or transient database issue caused a cleanup failure.
            logger.exception("Expired presentation cleanup failed")
        await asyncio.sleep(get_settings().cleanup_interval_minutes * 60)

@app.on_event("startup")
def startup(): init_db()
@app.on_event("startup")
async def start_cleanup():
    global cleanup_task
    cleanup_task=asyncio.create_task(cleanup_loop())
@app.on_event("shutdown")
async def stop_cleanup():
    if cleanup_task:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError): await cleanup_task
app.include_router(health.router); app.include_router(access.router); app.include_router(presentations.router); app.include_router(jobs.router)
app.include_router(llm.router)
