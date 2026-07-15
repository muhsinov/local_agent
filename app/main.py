import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.approvals import router as approvals_router
from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.api.errors import ApiError, error_response
from app.api.health import router as health_router
from app.api.model import router as model_router
from app.api.session import router as session_router
from app.api.vector_search import router as vector_router
from app.config import PROJECT_ROOT, Settings, get_settings
from app.database import initialize_database
from app.approval.repository import expire_pending_approvals, recover_stale_executions
from app.approval.operation_coordinator import ApprovalOperationCoordinator
from app.llm.ollama_client import OllamaClient
from app.agent.tool_operation_coordinator import ToolOperationCoordinator
from app.rag.index_manager import ensure_vector_directories, reconcile_vector_index
from app.rag.operation_coordinator import VectorOperationCoordinator
from app.services.document_recovery_service import reconcile_document_quarantine
from app.security.local_control_plane.middleware import LocalControlPlaneMiddleware
from app.security.local_control_plane.session_store import LocalSessionStore
from app.runtime.lifecycle import RuntimeLifecycle
from app.runtime.logging import SafeJsonlLogger
from app.runtime.middleware import RuntimeAdmissionMiddleware
from app.runtime.rate_limit import FixedWindowRateLimiter
from app.runtime.request_context import RequestContextMiddleware
from app.services.audit_service import write_audit_log


def ensure_runtime_directories(settings: Settings) -> None:
    settings.resolved_upload_directory.mkdir(parents=True, exist_ok=True)
    settings.resolved_extracted_text_directory.mkdir(parents=True, exist_ok=True)
    ensure_vector_directories(settings)
    initialize_database(settings)
    expire_pending_approvals(settings)
    recover_stale_executions(settings)
    reconcile_document_quarantine(settings)
    reconcile_vector_index(settings)


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    static_directory = (PROJECT_ROOT / "app" / "static").resolve()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = active_settings
        app.state.runtime_lifecycle.startup_ready = False
        created_client = False
        try:
            if not hasattr(app.state, "ollama_client") or app.state.ollama_client is None:
                app.state.ollama_client = OllamaClient(active_settings)
                created_client = True
            if not hasattr(app.state, "chat_semaphore") or app.state.chat_semaphore is None:
                app.state.chat_semaphore = asyncio.Semaphore(1)
            if not hasattr(app.state, "document_semaphore") or app.state.document_semaphore is None:
                app.state.document_semaphore = asyncio.Semaphore(1)
            if not hasattr(app.state, "vector_operation_coordinator") or app.state.vector_operation_coordinator is None:
                app.state.vector_operation_coordinator = VectorOperationCoordinator()
            if not hasattr(app.state, "tool_operation_coordinator") or app.state.tool_operation_coordinator is None:
                app.state.tool_operation_coordinator = ToolOperationCoordinator()
            if not hasattr(app.state, "approval_operation_coordinator") or app.state.approval_operation_coordinator is None:
                app.state.approval_operation_coordinator = ApprovalOperationCoordinator()
            ensure_runtime_directories(active_settings)
            app.state.runtime_lifecycle.startup_ready = True
            yield
        finally:
            shutdown_started = perf_counter()
            await app.state.runtime_lifecycle.begin_drain()
            remaining = max(0.0, active_settings.runtime_drain_timeout_seconds - (perf_counter() - shutdown_started))
            drained = await app.state.runtime_lifecycle.wait_for_active(remaining)
            if not drained:
                app.state.safe_logger.log(event="runtime_drain_timeout", request_id="", status_code=503, draining=True)
                write_audit_log(active_settings, action="runtime_drain_timeout", status="timeout", arguments={"status_code": 503, "draining": True})
            if getattr(app.state, "vector_operation_coordinator", None) is not None:
                remaining = max(0.0, active_settings.runtime_drain_timeout_seconds - (perf_counter() - shutdown_started))
                await app.state.vector_operation_coordinator.shutdown(timeout_seconds=remaining)
            if getattr(app.state, "tool_operation_coordinator", None) is not None:
                remaining = max(0.0, active_settings.runtime_drain_timeout_seconds - (perf_counter() - shutdown_started))
                await app.state.tool_operation_coordinator.shutdown(timeout_seconds=remaining)
            if getattr(app.state, "approval_operation_coordinator", None) is not None:
                remaining = max(0.0, active_settings.runtime_drain_timeout_seconds - (perf_counter() - shutdown_started))
                await app.state.approval_operation_coordinator.shutdown(timeout_seconds=remaining)
            if created_client:
                await app.state.ollama_client.close()
            app.state.safe_logger.close()

    app = FastAPI(title=active_settings.app_name, version=active_settings.app_version, lifespan=lifespan)
    app.state.settings = active_settings
    app.state.ollama_client = None
    app.state.chat_semaphore = None
    app.state.document_semaphore = None
    app.state.vector_operation_coordinator = None
    app.state.tool_operation_coordinator = None
    app.state.approval_operation_coordinator = None
    app.state.local_session_store = LocalSessionStore(
        ttl_seconds=active_settings.local_session_ttl_seconds,
        max_active=active_settings.local_session_max_active,
        session_bytes=active_settings.local_session_token_bytes,
        csrf_bytes=active_settings.local_csrf_token_bytes,
        max_csrf_tokens=active_settings.local_session_max_csrf_tokens,
    )
    app.state.runtime_lifecycle = RuntimeLifecycle()
    app.state.rate_limiter = FixedWindowRateLimiter()
    app.state.safe_logger = SafeJsonlLogger(
        active_settings.resolved_safe_log_directory,
        active_settings.safe_log_max_bytes,
        active_settings.safe_log_backup_count,
        active_settings.safe_logging_enabled,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[f"http://localhost:{active_settings.port}", f"http://127.0.0.1:{active_settings.port}", f"http://[::1]:{active_settings.port}"],
        allow_credentials=True,
        allow_methods=["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Authorization"],
    )
    app.add_middleware(RuntimeAdmissionMiddleware)
    app.add_middleware(LocalControlPlaneMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.mount("/static", StaticFiles(directory=static_directory), name="static")
    app.include_router(health_router)
    app.include_router(model_router)
    app.include_router(session_router)
    app.include_router(chat_router)
    app.include_router(approvals_router)
    app.include_router(documents_router)
    app.include_router(vector_router)

    @app.exception_handler(ApiError)
    async def handle_api_error(_: Request, exc: ApiError):
        return error_response(exc.status_code, exc.code, exc.message, exc.extra)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, __: RequestValidationError):
        return error_response(422, "VALIDATION_ERROR", "So'rov ma'lumotlari noto'g'ri.")

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, _: Exception):
        response = JSONResponse(status_code=500, content={"detail": {"code": "INTERNAL_SERVER_ERROR", "message": "Ichki server xatosi."}})
        request_id = getattr(request.state, "request_id", None)
        if request_id:
            response.headers["X-Request-ID"] = request_id
        return response

    @app.get("/", include_in_schema=False)
    def root() -> FileResponse:
        index_path = Path(static_directory / "index.html")
        return FileResponse(index_path)

    return app


app = create_app()
