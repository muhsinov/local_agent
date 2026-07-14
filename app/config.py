from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_name: str = Field(default="Local Agent Demo", alias="APP_NAME")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8000, alias="PORT", ge=1, le=65535)
    database_path: Path = Field(default=Path("data/local_agent.db"), alias="DATABASE_PATH")
    upload_directory: Path = Field(default=Path("data/uploads"), alias="UPLOAD_DIRECTORY")
    extracted_text_directory: Path = Field(default=Path("data/extracted"), alias="EXTRACTED_TEXT_DIRECTORY")
    vector_store_directory: Path = Field(default=Path("data/vector_store"), alias="VECTOR_STORE_DIRECTORY")
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="qwen3:1.7b", alias="OLLAMA_MODEL")
    ollama_keep_alive: str = Field(default="2m", alias="OLLAMA_KEEP_ALIVE")
    ollama_think: bool = Field(default=False, alias="OLLAMA_THINK")
    ollama_temperature: float = Field(default=0.2, alias="OLLAMA_TEMPERATURE", ge=0.0, le=2.0)
    ollama_num_ctx: int = Field(default=2048, alias="OLLAMA_NUM_CTX", ge=512, le=8192)
    ollama_num_predict: int = Field(default=512, alias="OLLAMA_NUM_PREDICT", ge=32, le=2048)
    chat_history_messages: int = Field(default=6, alias="CHAT_HISTORY_MESSAGES", ge=0, le=20)
    max_chat_message_chars: int = Field(default=4000, alias="MAX_CHAT_MESSAGE_CHARS", ge=100, le=20000)
    chat_busy_timeout_seconds: int = Field(default=5, alias="CHAT_BUSY_TIMEOUT_SECONDS", ge=1, le=30)
    document_busy_timeout_seconds: int = Field(default=10, alias="DOCUMENT_BUSY_TIMEOUT_SECONDS", ge=1, le=60)
    upload_chunk_size_kb: int = Field(default=256, alias="UPLOAD_CHUNK_SIZE_KB", ge=64, le=1024)
    max_pdf_pages: int = Field(default=100, alias="MAX_PDF_PAGES", ge=1, le=500)
    max_pdf_page_content_mb: int = Field(default=20, alias="MAX_PDF_PAGE_CONTENT_MB", ge=1, le=100)
    max_extracted_chars: int = Field(default=2_000_000, alias="MAX_EXTRACTED_CHARS", ge=1000, le=5_000_000)
    max_docx_uncompressed_mb: int = Field(default=50, alias="MAX_DOCX_UNCOMPRESSED_MB", ge=1, le=200)
    max_docx_zip_entries: int = Field(default=2000, alias="MAX_DOCX_ZIP_ENTRIES", ge=10, le=10000)
    max_docx_compression_ratio: int = Field(default=100, alias="MAX_DOCX_COMPRESSION_RATIO", ge=10, le=500)
    document_preview_chars: int = Field(default=5000, alias="DOCUMENT_PREVIEW_CHARS", ge=100, le=50000)
    max_document_list_limit: int = Field(default=100, alias="MAX_DOCUMENT_LIST_LIMIT", ge=1, le=500)
    max_original_filename_chars: int = Field(default=180, alias="MAX_ORIGINAL_FILENAME_CHARS", ge=20, le=255)
    request_timeout_seconds: int = Field(default=90, alias="REQUEST_TIMEOUT_SECONDS", ge=1, le=300)
    max_agent_iterations: int = Field(default=5, alias="MAX_AGENT_ITERATIONS", ge=1, le=10)
    max_file_size_mb: int = Field(default=10, alias="MAX_FILE_SIZE_MB", ge=1, le=100)

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

    @field_validator(
        "database_path",
        "upload_directory",
        "extracted_text_directory",
        "vector_store_directory",
        mode="after",
    )
    @classmethod
    def validate_paths(cls, value: Path) -> Path:
        if not str(value):
            raise ValueError("Path qiymati bo'sh bo'lishi mumkin emas.")
        return value

    @property
    def resolved_database_path(self) -> Path:
        return self.resolve_path(self.database_path)

    @property
    def resolved_upload_directory(self) -> Path:
        return self.resolve_path(self.upload_directory)

    @property
    def resolved_extracted_text_directory(self) -> Path:
        return self.resolve_path(self.extracted_text_directory)

    @property
    def resolved_vector_store_directory(self) -> Path:
        return self.resolve_path(self.vector_store_directory)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
