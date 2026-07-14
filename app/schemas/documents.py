from pydantic import BaseModel, Field


class DocumentMetadataResponse(BaseModel):
    id: int
    file_name: str
    file_type: str
    size_bytes: int
    status: str
    char_count: int
    page_count: int | None
    warning_code: str | None
    indexed: bool
    created_at: str


class DocumentListResponse(BaseModel):
    items: list[DocumentMetadataResponse]
    limit: int
    offset: int


class DocumentPreviewResponse(BaseModel):
    document_id: int
    text: str
    returned_chars: int
    total_chars: int
    truncated: bool
