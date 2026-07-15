from pydantic import BaseModel, ConfigDict, Field, field_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyArgs(_StrictModel):
    pass


class PaginationArgs(_StrictModel):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class DocumentIdArgs(_StrictModel):
    document_id: int = Field(ge=1)


class DocumentExcerptArgs(DocumentIdArgs):
    start_char: int = Field(default=0, ge=0)
    max_chars: int = Field(default=1500, ge=1, le=5000)


class SearchDocumentsArgs(_StrictModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=4, ge=1, le=20)
    document_ids: list[int] | None = None

    @field_validator("query", mode="after")
    @classmethod
    def trim_query(cls, value: str) -> str:
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


class ConversationMessagesArgs(_StrictModel):
    conversation_id: int = Field(ge=1)
    limit: int = Field(default=20, ge=1, le=100)


class RenameConversationArgs(_StrictModel):
    conversation_id: int = Field(ge=1)
    new_title: str = Field(min_length=1, max_length=80)

    @field_validator("new_title", mode="after")
    @classmethod
    def validate_new_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 80:
            raise ValueError("new_title noto'g'ri.")
        if any(ord(char) < 32 or ord(char) == 127 for char in normalized):
            raise ValueError("new_title control character saqlamasligi kerak.")
        if "\n" in normalized or "\r" in normalized:
            raise ValueError("new_title newline saqlamasligi kerak.")
        return normalized
