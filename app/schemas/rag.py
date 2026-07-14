from pydantic import BaseModel


class RagSourceResponse(BaseModel):
    citation: str
    chunk_id: int
    document_id: int
    file_name: str
    chunk_index: int
    score: float
    start_char: int
    end_char: int
    excerpt: str


class RagMetadataResponse(BaseModel):
    enabled: bool
    used: bool
    fallback: bool
    generation_id: str | None
    retrieved_count: int
    context_chars: int
    citations_present: bool
    invalid_citations_removed: int
