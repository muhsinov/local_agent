from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, model_validator, field_validator
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
    vector_store_directory: Path = Field(
        default=Path("data/vector_store"),
        alias="VECTOR_INDEX_DIRECTORY",
        validation_alias=AliasChoices("VECTOR_INDEX_DIRECTORY", "VECTOR_STORE_DIRECTORY"),
    )
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
    document_extraction_timeout_seconds: int = Field(
        default=60,
        alias="DOCUMENT_EXTRACTION_TIMEOUT_SECONDS",
        ge=5,
        le=300,
    )
    document_extraction_memory_mb: int = Field(
        default=512,
        alias="DOCUMENT_EXTRACTION_MEMORY_MB",
        ge=128,
        le=2048,
    )
    document_preview_chars: int = Field(default=5000, alias="DOCUMENT_PREVIEW_CHARS", ge=100, le=50000)
    max_document_list_limit: int = Field(default=100, alias="MAX_DOCUMENT_LIST_LIMIT", ge=1, le=500)
    max_original_filename_chars: int = Field(default=180, alias="MAX_ORIGINAL_FILENAME_CHARS", ge=20, le=255)
    request_timeout_seconds: int = Field(default=90, alias="REQUEST_TIMEOUT_SECONDS", ge=1, le=300)
    max_agent_iterations: int = Field(default=5, alias="MAX_AGENT_ITERATIONS", ge=1, le=10)
    max_file_size_mb: int = Field(default=10, alias="MAX_FILE_SIZE_MB", ge=1, le=100)
    tools_enabled: bool = Field(default=True, alias="TOOLS_ENABLED")
    agent_max_iterations: int = Field(default=5, alias="AGENT_MAX_ITERATIONS", ge=1, le=10)
    agent_total_timeout_seconds: int = Field(default=60, alias="AGENT_TOTAL_TIMEOUT_SECONDS", ge=5, le=300)
    agent_tool_timeout_seconds: int = Field(default=10, alias="AGENT_TOOL_TIMEOUT_SECONDS", ge=1, le=60)
    agent_max_tool_calls: int = Field(default=5, alias="AGENT_MAX_TOOL_CALLS", ge=1, le=20)
    agent_max_tool_result_chars: int = Field(default=12000, alias="AGENT_MAX_TOOL_RESULT_CHARS", ge=1000, le=50000)
    agent_max_single_tool_result_chars: int = Field(default=5000, alias="AGENT_MAX_SINGLE_TOOL_RESULT_CHARS", ge=200, le=20000)
    agent_max_argument_chars: int = Field(default=4000, alias="AGENT_MAX_ARGUMENT_CHARS", ge=100, le=10000)
    agent_max_path_chars: int = Field(default=500, alias="AGENT_MAX_PATH_CHARS", ge=50, le=1000)
    agent_include_tool_errors_in_prompt: bool = Field(default=True, alias="AGENT_INCLUDE_TOOL_ERRORS_IN_PROMPT")
    agent_require_explicit_tool_intent: bool = Field(default=True, alias="AGENT_REQUIRE_EXPLICIT_TOOL_INTENT")
    approvals_enabled: bool = Field(default=True, alias="APPROVALS_ENABLED")
    approval_expiry_seconds: int = Field(default=600, alias="APPROVAL_EXPIRY_SECONDS", ge=30, le=3600)
    approval_nonce_bytes: int = Field(default=32, alias="APPROVAL_NONCE_BYTES", ge=16, le=64)
    approval_max_pending: int = Field(default=20, alias="APPROVAL_MAX_PENDING", ge=1, le=100)
    approval_execution_timeout_seconds: int = Field(
        default=60,
        alias="APPROVAL_EXECUTION_TIMEOUT_SECONDS",
        ge=5,
        le=300,
    )
    approval_require_local_origin: bool = Field(default=True, alias="APPROVAL_REQUIRE_LOCAL_ORIGIN")
    approval_allow_rebuild_vector_index: bool = Field(default=True, alias="APPROVAL_ALLOW_REBUILD_VECTOR_INDEX")
    approval_allow_rename_conversation: bool = Field(default=True, alias="APPROVAL_ALLOW_RENAME_CONVERSATION")
    local_control_plane_enabled: bool = Field(default=True, alias="LOCAL_CONTROL_PLANE_ENABLED")
    local_session_ttl_seconds: int = Field(default=3600, alias="LOCAL_SESSION_TTL_SECONDS", ge=300, le=86400)
    local_session_max_active: int = Field(default=20, alias="LOCAL_SESSION_MAX_ACTIVE", ge=1, le=100)
    local_session_token_bytes: int = Field(default=32, alias="LOCAL_SESSION_TOKEN_BYTES", ge=16, le=64)
    local_csrf_token_bytes: int = Field(default=32, alias="LOCAL_CSRF_TOKEN_BYTES", ge=16, le=64)
    local_session_max_csrf_tokens: int = Field(default=16, alias="LOCAL_SESSION_MAX_CSRF_TOKENS", ge=1, le=64)
    local_require_csrf: bool = Field(default=True, alias="LOCAL_REQUIRE_CSRF")
    local_require_loopback_host: bool = Field(default=True, alias="LOCAL_REQUIRE_LOOPBACK_HOST")
    local_allow_non_browser_clients: bool = Field(default=False, alias="LOCAL_ALLOW_NON_BROWSER_CLIENTS")
    local_api_token: str = Field(default="", alias="LOCAL_API_TOKEN")
    direct_vector_mutations_enabled: bool = Field(default=False, alias="DIRECT_VECTOR_MUTATIONS_ENABLED")
    direct_document_delete_enabled: bool = Field(default=False, alias="DIRECT_DOCUMENT_DELETE_ENABLED")
    embedding_model_name: str = Field(
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        alias="EMBEDDING_MODEL_NAME",
    )
    embedding_device: str = Field(default="cpu", alias="EMBEDDING_DEVICE")
    embedding_dimension: int = Field(default=384, alias="EMBEDDING_DIMENSION", ge=64, le=4096)
    embedding_batch_size: int = Field(default=16, alias="EMBEDDING_BATCH_SIZE", ge=1, le=64)
    embedding_max_sequence_length: int = Field(
        default=128,
        alias="EMBEDDING_MAX_SEQUENCE_LENGTH",
        ge=32,
        le=512,
    )
    embedding_keep_loaded: bool = Field(default=False, alias="EMBEDDING_KEEP_LOADED")
    embedding_local_files_only: bool = Field(default=False, alias="EMBEDDING_LOCAL_FILES_ONLY")
    chunk_size_chars: int = Field(default=700, alias="CHUNK_SIZE_CHARS", ge=200, le=4000)
    chunk_overlap_chars: int = Field(default=100, alias="CHUNK_OVERLAP_CHARS", ge=0, le=1000)
    chunk_min_chars: int = Field(default=80, alias="CHUNK_MIN_CHARS", ge=20, le=1000)
    max_chunks_per_document: int = Field(default=5000, alias="MAX_CHUNKS_PER_DOCUMENT", ge=1, le=20000)
    vector_search_top_k: int = Field(default=4, alias="VECTOR_SEARCH_TOP_K", ge=1, le=20)
    vector_search_max_k: int = Field(default=20, alias="VECTOR_SEARCH_MAX_K", ge=1, le=100)
    vector_min_score: float = Field(default=0.15, alias="VECTOR_MIN_SCORE", ge=-1.0, le=1.0)
    vector_index_busy_timeout_seconds: int = Field(
        default=10,
        alias="VECTOR_INDEX_BUSY_TIMEOUT_SECONDS",
        ge=1,
        le=60,
    )
    vector_index_generation_retention: int = Field(
        default=2,
        alias="VECTOR_INDEX_GENERATION_RETENTION",
        ge=1,
        le=10,
    )
    rag_enabled: bool = Field(default=True, alias="RAG_ENABLED")
    rag_top_k: int = Field(default=4, alias="RAG_TOP_K", ge=1, le=10)
    rag_max_top_k: int = Field(default=8, alias="RAG_MAX_TOP_K", ge=1, le=20)
    rag_min_score: float = Field(default=0.20, alias="RAG_MIN_SCORE", ge=-1.0, le=1.0)
    rag_max_context_chars: int = Field(default=6000, alias="RAG_MAX_CONTEXT_CHARS", ge=500, le=20000)
    rag_max_chunk_chars: int = Field(default=1800, alias="RAG_MAX_CHUNK_CHARS", ge=200, le=4000)
    rag_max_sources: int = Field(default=4, alias="RAG_MAX_SOURCES", ge=1, le=10)
    rag_context_overlap_dedup: bool = Field(default=True, alias="RAG_CONTEXT_OVERLAP_DEDUP")
    rag_require_sources: bool = Field(default=False, alias="RAG_REQUIRE_SOURCES")
    rag_allow_fallback_without_index: bool = Field(default=True, alias="RAG_ALLOW_FALLBACK_WITHOUT_INDEX")
    rag_include_file_name: bool = Field(default=True, alias="RAG_INCLUDE_FILE_NAME")
    rag_include_chunk_index: bool = Field(default=True, alias="RAG_INCLUDE_CHUNK_INDEX")
    rag_citation_style: str = Field(default="brackets", alias="RAG_CITATION_STYLE")
    rag_busy_timeout_seconds: int = Field(default=10, alias="RAG_BUSY_TIMEOUT_SECONDS", ge=1, le=60)
    rag_prompt_max_chars: int = Field(default=8000, alias="RAG_PROMPT_MAX_CHARS", ge=1000, le=50000)
    rag_reserved_answer_tokens: int = Field(default=512, alias="RAG_RESERVED_ANSWER_TOKENS", ge=32, le=2048)
    rag_chars_per_token_estimate: int = Field(default=4, alias="RAG_CHARS_PER_TOKEN_ESTIMATE", ge=1, le=8)

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

    @field_validator("embedding_device", mode="after")
    @classmethod
    def validate_embedding_device(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized != "cpu":
            raise ValueError("EMBEDDING_DEVICE faqat cpu bo'lishi mumkin.")
        return normalized

    @field_validator("rag_citation_style", mode="after")
    @classmethod
    def validate_rag_citation_style(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized != "brackets":
            raise ValueError("RAG_CITATION_STYLE faqat brackets bo'lishi mumkin.")
        return normalized

    @model_validator(mode="after")
    def validate_related_values(self) -> "Settings":
        if self.chunk_overlap_chars >= self.chunk_size_chars:
            raise ValueError("CHUNK_OVERLAP_CHARS CHUNK_SIZE_CHARS dan kichik bo'lishi kerak.")
        if self.chunk_min_chars > self.chunk_size_chars:
            raise ValueError("CHUNK_MIN_CHARS CHUNK_SIZE_CHARS dan katta bo'lishi mumkin emas.")
        if self.vector_search_top_k > self.vector_search_max_k:
            raise ValueError("VECTOR_SEARCH_TOP_K VECTOR_SEARCH_MAX_K dan katta bo'lishi mumkin emas.")
        if self.rag_top_k > self.rag_max_top_k:
            raise ValueError("RAG_TOP_K RAG_MAX_TOP_K dan katta bo'lishi mumkin emas.")
        if self.rag_max_sources > self.rag_max_top_k:
            raise ValueError("RAG_MAX_SOURCES RAG_MAX_TOP_K dan katta bo'lishi mumkin emas.")
        if self.agent_tool_timeout_seconds > self.agent_total_timeout_seconds:
            raise ValueError("AGENT_TOOL_TIMEOUT_SECONDS AGENT_TOTAL_TIMEOUT_SECONDS dan katta bo'lishi mumkin emas.")
        if self.agent_max_tool_calls > self.agent_max_iterations:
            raise ValueError("AGENT_MAX_TOOL_CALLS AGENT_MAX_ITERATIONS dan katta bo'lishi mumkin emas.")
        if self.local_allow_non_browser_clients and len(self.local_api_token) < 32:
            raise ValueError("LOCAL_API_TOKEN kamida 32 character bo'lishi kerak.")
        return self

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
