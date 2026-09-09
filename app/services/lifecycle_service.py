"""Retention policy for generated presentation files and assets."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
from app.config import get_settings
from app.models.database import Presentation, SessionLocal

MANIFEST = "lifecycle.json"

def schedule_expiry(presentation_id: str) -> str:
    settings=get_settings(); expires_at=datetime.now(timezone.utc)+timedelta(hours=settings.file_retention_hours)
    folder=settings.local_storage_path / presentation_id; folder.mkdir(parents=True,exist_ok=True)
    (folder / MANIFEST).write_text(json.dumps({"presentation_id":presentation_id,"expires_at":expires_at.isoformat()}))
    return expires_at.isoformat()

def cleanup_expired_files(now: datetime | None = None) -> list[str]:
    """Delete only directories whose validated lifecycle manifest has expired."""
    now=now or datetime.now(timezone.utc); root=get_settings().local_storage_path
    removed=[]
    if not root.exists(): return removed
    for folder in root.iterdir():
        manifest=folder / MANIFEST
        if not folder.is_dir() or not manifest.is_file(): continue
        try:
            record=json.loads(manifest.read_text()); expires_at=datetime.fromisoformat(record["expires_at"])
            if expires_at.tzinfo is None: continue
            if expires_at > now: continue
            presentation_id=record["presentation_id"]
            if presentation_id != folder.name: continue
        except (ValueError, KeyError, json.JSONDecodeError):
            continue
        shutil.rmtree(folder)
        with SessionLocal() as db:
            presentation=db.get(Presentation,presentation_id)
            if presentation: presentation.status="EXPIRED"; db.commit()
        removed.append(presentation_id)
    return removed
