"""Small, server-authorized operational view for the SlideWeaver owner."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.config import get_settings
from app.models.database import ActiveAccessSession, GenerationJob, OAuthSession, Presentation, SessionLocal, User


def configured_admin_emails() -> set[str]:
    return {email.strip().lower() for email in get_settings().admin_emails.split(",") if email.strip()}


def admin_user_for_session(session_id: str) -> User | None:
    with SessionLocal() as db:
        session=db.get(OAuthSession, session_id)
        user=db.get(User, session.user_id) if session else None
        if user and user.email.lower() in configured_admin_emails():
            return user
        return None


def activity_snapshot() -> dict:
    """Return aggregate and per-user operational data without deck content."""
    cutoff=datetime.utcnow()-timedelta(minutes=get_settings().access_session_ttl_minutes)
    with SessionLocal() as db:
        active_rows=db.execute(
            select(OAuthSession, User, ActiveAccessSession)
            .join(User, OAuthSession.user_id == User.id)
            .join(ActiveAccessSession, OAuthSession.session_id == ActiveAccessSession.id)
            .where(ActiveAccessSession.last_seen_at >= cutoff)
            .order_by(ActiveAccessSession.last_seen_at.desc())
        ).all()
        latest_session_by_user={}
        for _, user, active_session in active_rows:
            existing=latest_session_by_user.get(user.id)
            if not existing or active_session.last_seen_at > existing[1].last_seen_at:
                latest_session_by_user[user.id]=(user, active_session)
        users=[]
        for user, active_session in latest_session_by_user.values():
            presentation_count=db.scalar(select(func.count(Presentation.id)).where(Presentation.user_id == user.id)) or 0
            latest_presentation=db.scalar(
                select(Presentation).where(Presentation.user_id == user.id).order_by(Presentation.updated_at.desc()).limit(1)
            )
            latest_job=db.scalar(
                select(GenerationJob)
                .join(Presentation, GenerationJob.presentation_id == Presentation.id)
                .where(Presentation.user_id == user.id)
                .order_by(GenerationJob.created_at.desc()).limit(1)
            )
            users.append({
                "name":user.display_name,
                "email":user.email,
                "last_seen_at":active_session.last_seen_at.isoformat(),
                "presentations":presentation_count,
                "latest_presentation":latest_presentation.title if latest_presentation else None,
                "latest_presentation_at":latest_presentation.updated_at.isoformat() if latest_presentation else None,
                "job_status":latest_job.status if latest_job else None,
                "current_stage":latest_job.current_stage if latest_job else None,
            })
        return {
            "active_users":len(users),
            "max_active_users":get_settings().access_max_active_users,
            "session_ttl_minutes":get_settings().access_session_ttl_minutes,
            "users":users,
        }
