from fastapi import APIRouter, Request, Response, status

from app.api.errors import ApiError
from app.services.audit_service import write_audit_log


router = APIRouter(tags=["session"])


@router.post("/session/bootstrap", status_code=status.HTTP_200_OK)
def bootstrap_session(request: Request, response: Response) -> dict:
    settings = request.app.state.settings
    created = request.app.state.local_session_store.create()
    if created is None:
        raise ApiError(429, "LOCAL_SESSION_LIMIT", "Faol local session limiti oshdi.")
    raw_session, raw_csrf, record = created
    response.set_cookie(
        key="local_agent_session",
        value=raw_session,
        max_age=settings.local_session_ttl_seconds,
        httponly=True,
        samesite="strict",
        secure=False,
        path="/",
    )
    write_audit_log(
        settings,
        action="local_session_create",
        status="created",
        arguments={"session_present": True, "browser": True, "host_category": "loopback"},
    )
    return {"csrf_token": raw_csrf, "expires_at": record.expires_at.isoformat()}
