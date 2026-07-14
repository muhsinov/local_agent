from pydantic import BaseModel, Field, field_validator


class VectorIndexStatusResponse(BaseModel):
    status: str
    active_generation: str | None
    dirty: bool
    document_count: int
    chunk_count: int
    embedding_model: str | None
    embedding_dimension: int | None


class VectorIndexRebuildResponse(VectorIndexStatusResponse):
    generation_id: str | None


class VectorSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=4, ge=1)
    document_ids: list[int] | None = None

    @field_validator("query", mode="after")
    @classmethod
    def validate_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query bo'sh bo'lishi mumkin emas.")
        return normalized

    @field_validator("document_ids", mode="after")
    @classmethod
    def validate_document_ids(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        unique = sorted(set(value))
        if len(unique) > 100 or any(item <= 0 for item in unique):
            raise ValueError("document_ids noto'g'ri.")
        return unique


class VectorSearchResultResponse(BaseModel):
    chunk_id: int
    document_id: int
    file_name: str
    chunk_index: int
    text: str
    score: float
    start_char: int
    end_char: int


class VectorSearchResponse(BaseModel):
    query: str
    results: list[VectorSearchResultResponse]
    generation_id: str
    embedding_model: str
    execution_time_ms: int
