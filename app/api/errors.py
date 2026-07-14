from dataclasses import dataclass

from fastapi.responses import JSONResponse


@dataclass
class ApiError(Exception):
    """Structured API error for stable JSON responses."""

    status_code: int
    code: str
    message: str


def error_payload(code: str, message: str) -> dict[str, dict[str, str]]:
    """Build the standard API error payload."""

    return {"detail": {"code": code, "message": message}}


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    """Return the standard JSON error response."""

    return JSONResponse(status_code=status_code, content=error_payload(code, message))
