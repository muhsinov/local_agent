import secrets
from time import perf_counter

from fastapi import Request

from app.runtime.logging import SafeJsonlLogger
from app.runtime.route_template import route_template


def request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    if value:
        return value
    value = secrets.token_hex(request.app.state.settings.request_id_bytes)
    request.state.request_id = value
    return value


class RequestContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive=receive)
        settings = request.app.state.settings
        request.state.request_id = secrets.token_hex(settings.request_id_bytes)
        started = perf_counter()
        status_code = 500

        async def send_with_context(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = list(message.get("headers", []))
                existing_headers = {key.lower() for key, _ in headers}
                headers.extend(
                    [
                        (b"x-request-id", request.state.request_id.encode("ascii")),
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"x-frame-options", b"DENY"),
                        (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                        (b"cross-origin-opener-policy", b"same-origin"),
                    ]
                )
                path = scope.get("path", "")
                if path.startswith("/static") or path == "/":
                    headers.append((b"content-security-policy", b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"))
                if (path == "/session/bootstrap" or path == "/chat" or path.startswith("/approvals/") or (path.startswith("/documents/") and path.endswith("/text"))) and b"cache-control" not in existing_headers:
                    headers.append((b"cache-control", b"no-store"))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_context)
        finally:
            logger: SafeJsonlLogger = getattr(request.app.state, "safe_logger", None)
            if logger is not None:
                logger.log(
                    event="request_complete",
                    request_id=request.state.request_id,
                    method=request.method,
                    route_template=route_template(request),
                    status_code=status_code,
                    duration_ms=int((perf_counter() - started) * 1000),
                    browser=bool(request.headers.get("origin") or request.headers.get("referer")),
                    authenticated=bool(getattr(request.state, "runtime_authenticated", False)),
                )
