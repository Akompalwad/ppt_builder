from fastapi import APIRouter, Depends, HTTPException, Query
from app.llm.gateway import LLMGateway
from app.api.routes.access import require_active_session

router=APIRouter(prefix="/api/llm",tags=["llm"])

@router.get("/status")
def llm_status(provider: str = Query("nvidia"), model: str | None = Query(None), _: str = Depends(require_active_session)):
    """A real inference probe; it never returns secrets or raw provider errors."""
    try:
        result=LLMGateway.from_settings(provider, model).healthcheck()
        return {"provider":provider, "model":model, **result}
    except Exception:
        raise HTTPException(status_code=503, detail="The selected LLM provider/model is not currently available.")
