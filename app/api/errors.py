from dataclasses import dataclass
from typing import Any

from fastapi.responses import JSONResponse


@dataclass
class ApiError(Exception):
    """Structured API error for stable JSON responses."""

    status_code: int
    code: str
    message: str
    extra: dict[str, Any] | None = None


def error_payload(code: str, message: str, extra: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Build the standard API error payload."""

    payload: dict[str, Any] = {"code": code, "message": message}
    if extra:
        payload.update(extra)
    return {"detail": payload}


def error_response(status_code: int, code: str, message: str, extra: dict[str, Any] | None = None) -> JSONResponse:
    """Return the standard JSON error response."""

    return JSONResponse(status_code=status_code, content=error_payload(code, message, extra))
