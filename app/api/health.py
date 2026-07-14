from fastapi import APIRouter, Response, status

from app.config import get_settings
from app.database import check_database


router = APIRouter(tags=["health"])


@router.get("/health")
def healthcheck(response: Response) -> dict[str, str]:
    settings = get_settings()
    database_ok = check_database(settings)
    if not database_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ok" if database_ok else "error",
        "app": "local-agent-demo",
        "version": settings.app_version,
        "database": "ok" if database_ok else "error",
    }
