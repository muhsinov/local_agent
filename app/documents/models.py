from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedDocument:
    """Document extraction result."""

    text: str
    char_count: int
    page_count: int | None
    status: str
    warning_code: str | None


@dataclass(frozen=True)
class DocumentRecord:
    """Database-facing document record."""

    id: int
    file_name: str
    file_path: str
    file_type: str
    size_bytes: int
    sha256: str | None
    status: str
    text_path: str | None
    char_count: int
    page_count: int | None
    warning_code: str | None
    indexed: bool
    created_at: str
    updated_at: str
