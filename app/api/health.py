from fastapi import APIRouter, Request, Response, status

from app.database import check_database
from app.rag.index_manager import get_vector_index_status
from app.services.audit_service import write_audit_log


router = APIRouter(tags=["health"])


@router.get("/live")
def liveness() -> dict[str, str]:
    return {"status": "live"}


@router.get("/ready")
def readiness(request: Request, response: Response) -> dict[str, str]:
    lifecycle = request.app.state.runtime_lifecycle
    if lifecycle.draining:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        write_audit_log(request.app.state.settings, action="runtime_ready_state", status="draining", arguments={"request_id": getattr(request.state, "request_id", ""), "status_code": 503, "draining": True})
        return {"status": "draining"}
    if not lifecycle.startup_ready or not check_database(request.app.state.settings):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        write_audit_log(request.app.state.settings, action="runtime_ready_state", status="not_ready", arguments={"request_id": getattr(request.state, "request_id", ""), "status_code": 503, "draining": False})
        return {"status": "not_ready"}
    try:
        get_vector_index_status(request.app.state.settings)
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        write_audit_log(request.app.state.settings, action="runtime_ready_state", status="not_ready", arguments={"request_id": getattr(request.state, "request_id", ""), "status_code": 503, "draining": False})
        return {"status": "not_ready"}
    write_audit_log(request.app.state.settings, action="runtime_ready_state", status="ready", arguments={"request_id": getattr(request.state, "request_id", ""), "status_code": 200, "draining": False})
    return {"status": "ready", "model": request.app.state.settings.ollama_model}


@router.get("/health")
def healthcheck(request: Request, response: Response) -> dict[str, str]:
    settings = request.app.state.settings
    database_ok = check_database(settings)
    if not database_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ok" if database_ok else "error",
        "app": "local-agent-demo",
        "version": settings.app_version,
        "database": "ok" if database_ok else "error",
    }
