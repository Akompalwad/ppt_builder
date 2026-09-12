"""Small, server-authorized operational view for the SlideWeaver owner."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path

from sqlalchemy import func, select

from app.config import get_settings
from app.models.database import ActiveAccessSession, FeedbackReport, GenerationJob, LoginAudit, OAuthSession, Presentation, PresentationVersion, SessionLocal, User


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
        feedback=db.scalars(select(FeedbackReport).order_by(FeedbackReport.created_at.desc()).limit(30)).all()
        return {
            "active_users":len(users),
            "max_active_users":get_settings().access_max_active_users,
            "session_ttl_minutes":get_settings().access_session_ttl_minutes,
            "users":users,
            "feedback":[{
                "id":report.id,
                "category":report.category,
                "message":report.message,
                "prompt":report.prompt,
                "error_details":report.error_details,
                "reply_to":report.reply_to,
                "created_at":report.created_at.isoformat(),
                "has_screenshot":bool(report.screenshot_path),
            } for report in feedback],
        }


def login_history(*, page: int=1, page_size: int=20, on_date: date | None=None) -> dict:
    """Return one page of audit events, optionally restricted to a UTC date."""
    page=max(1, page)
    page_size=min(max(1, page_size), 100)
    with SessionLocal() as db:
        filters=[]
        if on_date:
            start=datetime.combine(on_date, time.min)
            filters.extend((LoginAudit.created_at >= start, LoginAudit.created_at < start + timedelta(days=1)))
        total=db.scalar(select(func.count(LoginAudit.id)).where(*filters)) or 0
        events=db.scalars(
            select(LoginAudit)
            .where(*filters)
            .order_by(LoginAudit.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return {
            "events":[{"id":event.id, "email":event.email, "event":event.event, "created_at":event.created_at.isoformat()} for event in events],
            "page":page,
            "page_size":page_size,
            "total":total,
            "total_pages":max(1, (total + page_size - 1) // page_size),
            "date":on_date.isoformat() if on_date else None,
        }


def presentation_file_history(*, page: int=1, page_size: int=20) -> dict:
    """Return an admin-only index of deck ownership and generated server files."""
    page=max(1, page)
    page_size=min(max(1, page_size), 100)
    with SessionLocal() as db:
        total=db.scalar(select(func.count(Presentation.id))) or 0
        rows=db.execute(
            select(Presentation, User, PresentationVersion)
            .join(User, Presentation.user_id == User.id)
            .outerjoin(PresentationVersion, Presentation.current_version_id == PresentationVersion.id)
            .order_by(Presentation.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        presentations=[]
        for presentation, user, version in rows:
            filename="presentation.pptx"
            file_path=None
            file_exists=False
            if version:
                path=get_settings().local_storage_path / presentation.id / "versions" / str(version.version_number) / filename
                file_path=str(path)
                file_exists=path.is_file()
            presentations.append({
                "id":presentation.id,
                "title":presentation.title,
                "status":presentation.status,
                "requester_name":user.display_name,
                "requester_email":user.email,
                "created_at":presentation.created_at.isoformat(),
                "updated_at":presentation.updated_at.isoformat(),
                "version":version.version_number if version else None,
                "server_filename":filename if version else None,
                "server_path":file_path,
                "file_exists":file_exists,
            })
        return {
            "presentations":presentations,
            "page":page,
            "page_size":page_size,
            "total":total,
            "total_pages":max(1, (total + page_size - 1) // page_size),
        }


def _safe_feedback_screenshot(path_text: str | None) -> Path | None:
    if not path_text:
        return None
    root=get_settings().feedback_storage_path.resolve()
    path=Path(path_text).resolve()
    return path if path.is_relative_to(root) else None


def delete_feedback(feedback_id: str) -> bool:
    with SessionLocal() as db:
        report=db.get(FeedbackReport, feedback_id)
        if not report:
            return False
        screenshot=_safe_feedback_screenshot(report.screenshot_path)
        db.delete(report)
        db.commit()
    if screenshot:
        screenshot.unlink(missing_ok=True)
    return True


def purge_old_feedback(days: int) -> int:
    cutoff=datetime.utcnow()-timedelta(days=days)
    with SessionLocal() as db:
        reports=db.scalars(select(FeedbackReport).where(FeedbackReport.created_at < cutoff)).all()
        screenshots=[_safe_feedback_screenshot(report.screenshot_path) for report in reports]
        for report in reports:
            db.delete(report)
        db.commit()
    for screenshot in screenshots:
        if screenshot:
            screenshot.unlink(missing_ok=True)
    return len(reports)
