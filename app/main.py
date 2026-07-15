import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.approvals import router as approvals_router
from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.api.errors import ApiError, error_response
from app.api.health import router as health_router
from app.api.model import router as model_router
from app.api.vector_search import router as vector_router
from app.config import PROJECT_ROOT, Settings, get_settings
from app.database import initialize_database
from app.approval.repository import expire_pending_approvals
from app.llm.ollama_client import OllamaClient
from app.agent.tool_operation_coordinator import ToolOperationCoordinator
from app.rag.index_manager import ensure_vector_directories, reconcile_vector_index
from app.rag.operation_coordinator import VectorOperationCoordinator
from app.services.document_recovery_service import reconcile_document_quarantine


def ensure_runtime_directories(settings: Settings) -> None:
    settings.resolved_upload_directory.mkdir(parents=True, exist_ok=True)
    settings.resolved_extracted_text_directory.mkdir(parents=True, exist_ok=True)
    ensure_vector_directories(settings)
    initialize_database(settings)
    expire_pending_approvals(settings)
    reconcile_document_quarantine(settings)
    reconcile_vector_index(settings)


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    static_directory = (PROJECT_ROOT / "app" / "static").resolve()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = active_settings
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
            ensure_runtime_directories(active_settings)
            yield
        finally:
            if getattr(app.state, "vector_operation_coordinator", None) is not None:
                await app.state.vector_operation_coordinator.shutdown()
            if getattr(app.state, "tool_operation_coordinator", None) is not None:
                await app.state.tool_operation_coordinator.shutdown()
            if created_client:
                await app.state.ollama_client.close()

    app = FastAPI(title=active_settings.app_name, version=active_settings.app_version, lifespan=lifespan)
    app.state.settings = active_settings
    app.state.ollama_client = None
    app.state.chat_semaphore = None
    app.state.document_semaphore = None
    app.state.vector_operation_coordinator = None
    app.state.tool_operation_coordinator = None
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost",
            "http://localhost:3000",
            "http://127.0.0.1",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:8000",
            "http://localhost:8000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/static", StaticFiles(directory=static_directory), name="static")
    app.include_router(health_router)
    app.include_router(model_router)
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

    @app.get("/", include_in_schema=False)
    def root() -> FileResponse:
        index_path = Path(static_directory / "index.html")
        return FileResponse(index_path)

    return app


app = create_app()
