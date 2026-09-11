"""Configurable, lightweight active-session gate for test deployments."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.config import get_settings
from app.models.database import ActiveAccessSession, OAuthSession, SessionLocal


LIMIT_MESSAGE="Login after sometime — user limit is exceeded at this time."


class AccessService:
    def claim(self, session_id: str) -> tuple[bool, int]:
        settings=get_settings()
        if not settings.access_gate_enabled:
            return True, 0
        now=datetime.utcnow()
        cutoff=now-timedelta(minutes=settings.access_session_ttl_minutes)
        with SessionLocal() as db:
            db.query(ActiveAccessSession).filter(ActiveAccessSession.last_seen_at < cutoff).delete()
            existing=db.get(ActiveAccessSession, session_id)
            if existing:
                existing.last_seen_at=now
                db.commit()
                if settings.auth_mode.lower() == "google":
                    active=db.query(ActiveAccessSession).join(OAuthSession, ActiveAccessSession.id == OAuthSession.session_id).count()
                    return True, active
                return True, db.query(ActiveAccessSession).count()
            # Once Google OAuth is enabled, only authenticated OAuth sessions
            # consume the configured user limit. This deliberately excludes
            # stale browser-only sessions created while testing mode was on.
            active=(
                db.query(ActiveAccessSession).join(OAuthSession, ActiveAccessSession.id == OAuthSession.session_id).count()
                if settings.auth_mode.lower() == "google" else db.query(ActiveAccessSession).count()
            )
            if active >= settings.access_max_active_users:
                db.commit()
                return False, active
            db.add(ActiveAccessSession(id=session_id, last_seen_at=now))
            db.commit()
            return True, active+1
