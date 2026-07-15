from datetime import datetime, timezone
from math import ceil

from fastapi import APIRouter, Request, Response, status

from app.api.errors import ApiError
from app.services.audit_service import write_audit_log


router = APIRouter(tags=["session"])


@router.post("/session/bootstrap", status_code=status.HTTP_200_OK)
def bootstrap_session(request: Request, response: Response) -> dict:
    settings = request.app.state.settings
    existing_session = request.cookies.get("local_agent_session")
    session_reused = bool(existing_session and request.app.state.local_session_store.has_session(existing_session))
    created = request.app.state.local_session_store.bootstrap(existing_session)
    if created is None:
        raise ApiError(429, "LOCAL_SESSION_LIMIT", "Faol local session limiti oshdi.")
    raw_session, raw_csrf, record = created
    remaining_seconds = max(0, ceil((record.expires_at - datetime.now(timezone.utc)).total_seconds()))
    response.set_cookie(
        key="local_agent_session",
        value=raw_session,
        max_age=remaining_seconds,
        httponly=True,
        samesite="strict",
        secure=False,
        path="/",
    )
    write_audit_log(
        settings,
        action="local_session_create",
        status="created",
        arguments={
            "browser": bool(request.headers.get("origin") or request.headers.get("referer")),
            "origin_present": bool(request.headers.get("origin")),
            "session_reused": session_reused,
            "session_created": not session_reused,
            "host_category": "loopback",
        },
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return {"csrf_token": raw_csrf, "expires_at": record.expires_at.isoformat()}
