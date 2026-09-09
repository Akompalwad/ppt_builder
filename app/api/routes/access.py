from fastapi import APIRouter, Header, HTTPException, Query

from app.config import get_settings
from app.services.access_service import AccessService, LIMIT_MESSAGE

router=APIRouter(prefix="/api/access", tags=["access"])
service=AccessService()


def require_active_session(
    x_deckforge_session: str | None = Header(default=None),
    deckforge_session: str | None = Query(default=None),
) -> str:
    """Protect work-creating API calls even when bypassing the Streamlit UI."""
    session_id=x_deckforge_session or deckforge_session
    if not get_settings().access_gate_enabled:
        return session_id or "development"
    if not session_id or len(session_id) > 64:
        raise HTTPException(status_code=401, detail="A valid browser session is required.")
    allowed, _=service.claim(session_id)
    if not allowed:
        raise HTTPException(status_code=429, detail=LIMIT_MESSAGE)
    return session_id


@router.post("/claim")
def claim_access(x_deckforge_session: str | None = Header(default=None)):
    if not x_deckforge_session or len(x_deckforge_session) > 64:
        raise HTTPException(status_code=400, detail="A valid browser session is required.")
    allowed, active=service.claim(x_deckforge_session)
    if not allowed:
        raise HTTPException(status_code=429, detail=LIMIT_MESSAGE)
    return {"allowed":True, "active_users":active}
