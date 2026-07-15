from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.security.local_control_plane.origin import validate_host, validate_origin, validate_referer
from app.services.audit_service import write_audit_log
from app.runtime.route_template import route_template


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class LocalControlPlaneMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = request.app.state.settings
        if not settings.local_control_plane_enabled:
            return await call_next(request)

        if settings.local_require_loopback_host and not validate_host(request.headers.get("host"), settings.port):
            return self._deny(request, "LOCAL_HOST_DENIED", "Local Host talab qilinadi.", "host")

        origin = request.headers.get("origin")
        referer = request.headers.get("referer")
        fetch_site = request.headers.get("sec-fetch-site")
        if request.url.path == "/session/bootstrap" and request.method == "POST":
            if origin is not None and not validate_origin(origin, settings.port):
                return self._deny(request, "LOCAL_ORIGIN_DENIED", "Local Origin talab qilinadi.", "origin")
            if origin is None and referer is not None and not validate_referer(referer, settings.port):
                return self._deny(request, "LOCAL_ORIGIN_DENIED", "Local Referer talab qilinadi.", "referer")
            if origin is None and referer is None:
                return self._deny(request, "LOCAL_ORIGIN_DENIED", "Bootstrap uchun local Origin yoki Referer talab qilinadi.", "origin_missing")
            if fetch_site is not None and fetch_site != "same-origin":
                return self._deny(request, "LOCAL_ORIGIN_DENIED", "Local same-origin request talab qilinadi.", "sec_fetch_site")
            request.state.runtime_identity = "bootstrap-global"
            request.state.runtime_authenticated = False
            return await call_next(request)

        if request.method not in SAFE_METHODS:
            if origin is not None and not validate_origin(origin, settings.port):
                return self._deny(request, "LOCAL_ORIGIN_DENIED", "Local Origin talab qilinadi.", "origin")
            if origin is None and referer is not None and not validate_referer(referer, settings.port):
                return self._deny(request, "LOCAL_ORIGIN_DENIED", "Local Referer talab qilinadi.", "referer")
            if fetch_site is not None and fetch_site != "same-origin":
                return self._deny(request, "LOCAL_ORIGIN_DENIED", "Local same-origin request talab qilinadi.", "sec_fetch_site")

            raw_session = request.cookies.get("local_agent_session")
            is_browser = origin is not None or referer is not None or raw_session is not None
            if not is_browser and settings.local_allow_non_browser_clients:
                authorization = request.headers.get("authorization", "")
                token = authorization[7:] if authorization.startswith("Bearer ") else ""
                import hmac

                if not settings.local_api_token or not hmac.compare_digest(token, settings.local_api_token):
                    return self._deny(request, "LOCAL_SESSION_REQUIRED", "Local session talab qilinadi.", "api_token")
                request.state.runtime_identity = "local-api-client"
                request.state.runtime_authenticated = True
            elif not request.app.state.local_session_store.has_session(raw_session):
                return self._deny(request, "LOCAL_SESSION_REQUIRED", "Local session talab qilinadi.", "session")
            else:
                request.state.runtime_identity = request.app.state.local_session_store.session_identity(raw_session)
                request.state.runtime_authenticated = True

            if settings.local_require_csrf and not (not is_browser and settings.local_allow_non_browser_clients):
                csrf = request.headers.get("x-csrf-token")
                if not csrf:
                    return self._deny(request, "CSRF_TOKEN_REQUIRED", "CSRF token talab qilinadi.", "csrf_missing")
                if not request.app.state.local_session_store.validate(raw_session, csrf):
                    return self._deny(request, "CSRF_TOKEN_INVALID", "CSRF token noto'g'ri.", "csrf_invalid")
        if not hasattr(request.state, "runtime_identity"):
            request.state.runtime_identity = request.app.state.local_session_store.session_identity(request.cookies.get("local_agent_session")) or "local-read"
            request.state.runtime_authenticated = bool(request.state.runtime_identity != "local-read")
        return await call_next(request)

    @staticmethod
    def _deny(request: Request, code: str, message: str, reason: str):
        settings = request.app.state.settings
        try:
            write_audit_log(
                settings,
                action="local_request_denied",
                status=code,
                arguments={
                    "method": request.method,
                    "route_template": route_template(request),
                    "reason_code": reason,
                    "browser": bool(request.headers.get("origin") or request.headers.get("referer")),
                    "session_present": bool(request.cookies.get("local_agent_session")),
                    "origin_present": bool(request.headers.get("origin")),
                    "host_category": "loopback" if validate_host(request.headers.get("host"), settings.port) else "external",
                },
            )
        except Exception:
            pass
        return JSONResponse(status_code=401 if code == "LOCAL_SESSION_REQUIRED" else 403, content={"detail": {"code": code, "message": message}})
