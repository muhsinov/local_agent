from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.health import router as health_router
from app.config import PROJECT_ROOT, Settings, get_settings
from app.database import initialize_database


def ensure_runtime_directories(settings: Settings) -> None:
    settings.resolved_upload_directory.mkdir(parents=True, exist_ok=True)
    settings.resolved_vector_store_directory.mkdir(parents=True, exist_ok=True)
    initialize_database(settings)


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    static_directory = (PROJECT_ROOT / "app" / "static").resolve()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = active_settings
        ensure_runtime_directories(active_settings)
        yield

    app = FastAPI(title=active_settings.app_name, version=active_settings.app_version, lifespan=lifespan)
    app.state.settings = active_settings
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

    @app.get("/", include_in_schema=False)
    def root() -> FileResponse:
        index_path = Path(static_directory / "index.html")
        return FileResponse(index_path)

    return app


app = create_app()
