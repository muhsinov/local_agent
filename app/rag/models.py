from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    document_id: int
    chunk_index: int
    text: str
    start_char: int
    end_char: int
    char_count: int
    content_sha256: str


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: int
    document_id: int
    file_name: str
    chunk_index: int
    text: str
    score: float
    start_char: int
    end_char: int


@dataclass(frozen=True)
class VectorIndexStateSnapshot:
    status: str
    active_generation: str | None
    dirty: bool
    document_count: int
    chunk_count: int
    embedding_model: str | None
    embedding_dimension: int | None


@dataclass(frozen=True)
class VectorIndexManifest:
    format_version: int
    generation_id: str
    embedding_model: str
    embedding_dimension: int
    metric: str
    faiss_index_type: str
    chunk_size_chars: int
    chunk_overlap_chars: int
    chunk_min_chars: int
    document_count: int
    chunk_count: int
    created_at: str
