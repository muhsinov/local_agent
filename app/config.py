from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_name: str = Field(default="Local Agent Demo", alias="APP_NAME")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    database_path: Path = Field(default=Path("data/local_agent.db"), alias="DATABASE_PATH")
    upload_directory: Path = Field(default=Path("data/uploads"), alias="UPLOAD_DIRECTORY")
    vector_store_directory: Path = Field(default=Path("data/vector_store"), alias="VECTOR_STORE_DIRECTORY")
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="qwen3:1.7b", alias="OLLAMA_MODEL")
    request_timeout_seconds: int = Field(default=90, alias="REQUEST_TIMEOUT_SECONDS")
    max_agent_iterations: int = Field(default=5, alias="MAX_AGENT_ITERATIONS")
    max_file_size_mb: int = Field(default=10, alias="MAX_FILE_SIZE_MB")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
        extra="ignore",
    )

    def resolve_path(self, value: Path) -> Path:
        if value.is_absolute():
            return value
        return (PROJECT_ROOT / value).resolve()

    @property
    def resolved_database_path(self) -> Path:
        return self.resolve_path(self.database_path)

    @property
    def resolved_upload_directory(self) -> Path:
        return self.resolve_path(self.upload_directory)

    @property
    def resolved_vector_store_directory(self) -> Path:
        return self.resolve_path(self.vector_store_directory)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
