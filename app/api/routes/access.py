from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.config import get_settings
from app.models.database import OAuthSession, SessionLocal
from app.services.access_service import AccessService, LIMIT_MESSAGE

router=APIRouter(prefix="/api/access", tags=["access"])
service=AccessService()


def require_active_session(
    x_slideweaver_session: str | None = Header(default=None),
    slideweaver_session: str | None = Query(default=None),
    x_deckforge_session: str | None = Header(default=None),
    deckforge_session: str | None = Query(default=None),
) -> str:
    """Protect work-creating API calls even when bypassing the Streamlit UI."""
    # Legacy aliases keep pre-rename download links functional during their
    # retention period.
    session_id=x_slideweaver_session or slideweaver_session or x_deckforge_session or deckforge_session
    settings=get_settings()
    if settings.auth_mode.lower() == "google":
        if not session_id or len(session_id) > 64:
            raise HTTPException(status_code=401, detail="Sign in with Google to continue.")
        with SessionLocal() as db:
            if not db.get(OAuthSession, session_id):
                raise HTTPException(status_code=401, detail="Sign in with Google to continue.")
        allowed, _=service.claim(session_id)
        if not allowed:
            raise HTTPException(status_code=429, detail=LIMIT_MESSAGE)
        return session_id
    if not settings.access_gate_enabled:
        return session_id or "development"
    if not session_id or len(session_id) > 64:
        raise HTTPException(status_code=401, detail="A valid browser session is required.")
    allowed, _=service.claim(session_id)
    if not allowed:
        raise HTTPException(status_code=429, detail=LIMIT_MESSAGE)
    return session_id


@router.post("/claim")
def claim_access(
    session_id: str = Depends(require_active_session),
):
    allowed, active=service.claim(session_id)
    if not allowed:
        raise HTTPException(status_code=429, detail=LIMIT_MESSAGE)
    return {"allowed":True, "active_users":active}
