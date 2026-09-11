"""Google OAuth sign-in for the public SlideWeaver deployment."""
from __future__ import annotations

from datetime import datetime, timedelta
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.config import get_settings
from app.models.database import ActiveAccessSession, OAuthCallbackTicket, OAuthLoginState, OAuthSession, SessionLocal, User
from app.services.access_service import AccessService, LIMIT_MESSAGE
from app.services.admin_service import configured_admin_emails

router=APIRouter(prefix="/api/auth", tags=["auth"])
GOOGLE_AUTHORIZE_URL="https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL="https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL="https://openidconnect.googleapis.com/v1/userinfo"


def _configured() -> bool:
    settings=get_settings()
    return bool(settings.google_client_id and settings.google_client_secret and settings.google_redirect_uri)


def _public_redirect(*, ticket: str | None=None, error: str | None=None) -> RedirectResponse:
    settings=get_settings()
    query=urlencode({key:value for key, value in {"oauth_ticket":ticket, "auth_error":error}.items() if value})
    return RedirectResponse(f"{settings.app_public_url.rstrip('/')}/?{query}" if query else settings.app_public_url.rstrip("/") + "/")


@router.get("/me")
def current_user(x_slideweaver_session: str | None = Header(default=None)):
    settings=get_settings()
    if settings.auth_mode.lower() != "google":
        return {"authenticated":False, "mode":settings.auth_mode, "configured":False}
    if not x_slideweaver_session:
        return {"authenticated":False, "mode":"google", "configured":_configured()}
    with SessionLocal() as db:
        session=db.get(OAuthSession, x_slideweaver_session)
        user=db.get(User, session.user_id) if session else None
        if not user:
            return {"authenticated":False, "mode":"google", "configured":_configured()}
        return {"authenticated":True, "mode":"google", "configured":True, "email":user.email, "name":user.display_name, "is_admin":user.email.lower() in configured_admin_emails()}


@router.get("/google/start")
def google_start():
    if get_settings().auth_mode.lower() != "google" or not _configured():
        raise HTTPException(status_code=503, detail="Google sign-in is not configured on this server.")
    state=secrets.token_urlsafe(32)
    with SessionLocal() as db:
        cutoff=datetime.utcnow()-timedelta(minutes=get_settings().google_oauth_state_ttl_minutes)
        db.query(OAuthLoginState).filter(OAuthLoginState.created_at < cutoff).delete()
        db.add(OAuthLoginState(state=state))
        db.commit()
    settings=get_settings()
    params={
        "client_id":settings.google_client_id, "redirect_uri":settings.google_redirect_uri,
        "response_type":"code", "scope":"openid email profile", "state":state,
        "prompt":"select_account",
    }
    return RedirectResponse(f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}")


@router.get("/google/callback")
def google_callback(code: str | None = Query(default=None), state: str | None = Query(default=None), error: str | None = Query(default=None)):
    if error:
        return _public_redirect(error="Google sign-in was cancelled or denied.")
    if not code or not state or not _configured():
        return _public_redirect(error="Google sign-in could not be completed.")
    settings=get_settings()
    with SessionLocal() as db:
        state_row=db.get(OAuthLoginState, state)
        if not state_row or state_row.created_at < datetime.utcnow()-timedelta(minutes=settings.google_oauth_state_ttl_minutes):
            if state_row:
                db.delete(state_row); db.commit()
            return _public_redirect(error="Your sign-in request expired. Please try again.")
        db.delete(state_row)
        db.commit()
    try:
        token_response=httpx.post(GOOGLE_TOKEN_URL, data={
            "code":code, "client_id":settings.google_client_id, "client_secret":settings.google_client_secret,
            "redirect_uri":settings.google_redirect_uri, "grant_type":"authorization_code",
        }, timeout=15)
        token_response.raise_for_status()
        access_token=token_response.json().get("access_token")
        if not access_token:
            raise ValueError("Google did not return an access token")
        profile_response=httpx.get(GOOGLE_USERINFO_URL, headers={"Authorization":f"Bearer {access_token}"}, timeout=15)
        profile_response.raise_for_status()
        profile=profile_response.json()
        email=str(profile.get("email") or "").strip().lower()
        if not email or profile.get("email_verified") is not True:
            raise ValueError("Google did not provide a verified email")
    except (httpx.HTTPError, ValueError):
        return _public_redirect(error="Google sign-in could not be verified. Please try again.")
    session_id=secrets.token_urlsafe(32)
    allowed, _=AccessService().claim(session_id)
    if not allowed:
        return _public_redirect(error=LIMIT_MESSAGE)
    ticket=secrets.token_urlsafe(32)
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email==email))
        if not user:
            user=User(email=email, display_name=str(profile.get("name") or email.split("@", 1)[0])[:255], provider="google")
            db.add(user); db.flush()
        db.add(OAuthSession(session_id=session_id, user_id=user.id))
        db.add(OAuthCallbackTicket(ticket=ticket, session_id=session_id))
        db.commit()
    return _public_redirect(ticket=ticket)


@router.post("/session")
def exchange_callback_ticket(ticket: str):
    with SessionLocal() as db:
        row=db.get(OAuthCallbackTicket, ticket)
        if not row or row.created_at < datetime.utcnow()-timedelta(minutes=get_settings().google_oauth_state_ttl_minutes):
            if row:
                db.delete(row); db.commit()
            raise HTTPException(status_code=401, detail="This sign-in link has expired. Please sign in again.")
        session_id=row.session_id
        db.delete(row)
        db.commit()
    return {"session_id":session_id}


@router.post("/logout")
def logout(x_slideweaver_session: str | None = Header(default=None)):
    if x_slideweaver_session:
        with SessionLocal() as db:
            oauth_session=db.get(OAuthSession, x_slideweaver_session)
            if oauth_session:
                # A Google account can have sessions from more than one tab or
                # browser. Signing out must revoke them all, otherwise the
                # Admin panel still correctly sees that account as active.
                session_ids=list(db.scalars(select(OAuthSession.session_id).where(OAuthSession.user_id == oauth_session.user_id)))
                for session_id in session_ids:
                    active_session=db.get(ActiveAccessSession, session_id)
                    if active_session:
                        db.delete(active_session)
                db.query(OAuthSession).filter(OAuthSession.user_id == oauth_session.user_id).delete()
            else:
                access_session=db.get(ActiveAccessSession, x_slideweaver_session)
                if access_session:
                    db.delete(access_session)
            db.commit()
    return {"status":"logged_out"}
