from fastapi import Request
from starlette.responses import JSONResponse

from app.runtime.route_template import route_template
from app.runtime.policy import direct_action_disabled
from app.services.audit_service import write_audit_log


def _group_and_limits(request: Request, settings):
    path = request.url.path
    method = request.method
    if path == "/session/bootstrap" and method == "POST":
        return "bootstrap", settings.rate_limit_bootstrap_requests, settings.rate_limit_bootstrap_window_seconds
    if path == "/chat" and method == "POST":
        return "chat", settings.rate_limit_chat_requests, settings.rate_limit_chat_window_seconds
    if path == "/documents/upload" and method == "POST":
        return "upload", settings.rate_limit_upload_requests, settings.rate_limit_upload_window_seconds
    if path.startswith("/approvals/") and method == "POST" and path.rsplit("/", 1)[-1] in {"approve", "reject", "result"}:
        return "approval", settings.rate_limit_approval_requests, settings.rate_limit_approval_window_seconds
    if (path.startswith("/documents/") and path.endswith("/index") and method == "POST") or path == "/vector-index/rebuild" or (path.startswith("/documents/") and method == "DELETE"):
        return "direct_mutation", settings.rate_limit_direct_mutation_requests, settings.rate_limit_direct_mutation_window_seconds
    return "read", settings.rate_limit_read_requests, settings.rate_limit_read_window_seconds


class RuntimeAdmissionMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive=receive)
        settings = request.app.state.settings
        if not settings.runtime_resilience_enabled:
            await self.app(scope, receive, send)
            return

        lifecycle = request.app.state.runtime_lifecycle
        path = request.url.path
        group, limit, window = _group_and_limits(request, settings)
        drain_allowed = path in {"/live", "/ready", "/health", "/vector-index/status"} or path.startswith("/static") or (request.method == "GET" and path.startswith("/approvals/"))
        if settings.runtime_reject_during_drain and lifecycle.draining and not drain_allowed:
            self._audit(request, "runtime_draining", 503, None, None, True)
            await self._respond(request, send, 503, "SERVER_DRAINING", "Server draining holatida.", {"retry-after": "5"})
            return

        content_type = request.headers.get("content-type", "").lower()
        content_length = request.headers.get("content-length")
        too_large = False
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not content_type.startswith("multipart/") and content_length is not None:
            try:
                too_large = int(content_length) > settings.request_body_max_bytes
            except ValueError:
                too_large = False
        if too_large:
            self._audit(request, "request_body_rejected", 413, "REQUEST_BODY_TOO_LARGE", None, False)
            await self._respond(request, send, 413, "REQUEST_BODY_TOO_LARGE", "Request body limiti oshdi.", {})
            return

        disabled, _ = direct_action_disabled(request, settings)
        if disabled:
            self._audit(request, "direct_action_denied", 403, "DIRECT_ACTION_DISABLED", "direct_mutation", False)
            await self._respond(request, send, 403, "DIRECT_ACTION_DISABLED", "Direct action o'chirilgan.", {})
            return

        if settings.rate_limit_enabled and path != "/live":
            identity = getattr(request.state, "runtime_identity", "local-read")
            result = request.app.state.rate_limiter.check(group, identity, limit, window)
            if not result.allowed:
                self._audit(request, "request_rate_limited", 429, "RATE_LIMIT_EXCEEDED", group, False, result.limit, result.reset_seconds)
                request.app.state.safe_logger.log(event="request_rate_limited", request_id=request.state.request_id, method=request.method, route_template=route_template(request), status_code=429, rate_limit_group=group, limit=limit, retry_after_seconds=result.reset_seconds)
                await self._respond(request, send, 429, "RATE_LIMIT_EXCEEDED", "Request rate limitidan oshdi.", {"retry-after": str(result.reset_seconds), "x-ratelimit-limit": str(result.limit), "x-ratelimit-remaining": "0", "x-ratelimit-reset": str(result.reset_seconds)})
                return

        entered = await lifecycle.enter() if not drain_allowed else True
        if not entered:
            await self._respond(request, send, 503, "SERVER_DRAINING", "Server draining holatida.", {"retry-after": "5"})
            return
        try:
            await self.app(scope, receive, send)
        finally:
            if not drain_allowed:
                await lifecycle.exit()

    @staticmethod
    def _audit(request, action, status_code, error_code, group, draining, limit=None, retry_after=None):
        try:
            write_audit_log(
                request.app.state.settings,
                action=action,
                status=error_code or action,
                arguments={
                    "request_id": getattr(request.state, "request_id", ""),
                    "method": request.method,
                    "route_template": route_template(request),
                    "status_code": status_code,
                    "error_code": error_code,
                    "rate_limit_group": group,
                    "limit": limit,
                    "retry_after_seconds": retry_after,
                    "draining": draining,
                },
            )
        except Exception:
            pass

    @staticmethod
    async def _respond(request: Request, send, status_code: int, code: str, message: str, headers: dict[str, str]):
        body = ('{"detail":{"code":"' + code + '","message":"' + message + '"}}').encode("utf-8")
        response_headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
        response_headers.extend((key.encode(), value.encode()) for key, value in headers.items())
        await send({"type": "http.response.start", "status": status_code, "headers": response_headers})
        await send({"type": "http.response.body", "body": body, "more_body": False})
