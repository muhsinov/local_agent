from fastapi import APIRouter, Request, Response, status

from app.database import check_database


router = APIRouter(tags=["health"])


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
