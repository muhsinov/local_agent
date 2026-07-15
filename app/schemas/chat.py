from pydantic import BaseModel, Field, field_validator

from app.schemas.rag import RagMetadataResponse, RagSourceResponse


class ChatRequest(BaseModel):
    """Incoming chat request payload."""

    message: str = Field(min_length=1)
    conversation_id: int | None = Field(default=None, ge=1)
    use_rag: bool | None = None
    use_tools: bool | None = None
    document_ids: list[int] | None = None

    @field_validator("message", mode="before")
    @classmethod
    def trim_message(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Message matn bo'lishi kerak.")
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Bo'sh xabar yuborib bo'lmaydi.")
        return trimmed

    @field_validator("document_ids", mode="after")
    @classmethod
    def validate_document_ids(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        unique = sorted(set(value))
        if len(unique) > 100 or any(item <= 0 for item in unique):
            raise ValueError("document_ids noto'g'ri.")
        return unique


class UsageSummary(BaseModel):
    """Usage values returned to the frontend."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class ChatResponse(BaseModel):
    """Outgoing chat response payload."""

    conversation_id: int
    answer: str
    model: str
    sources: list[RagSourceResponse] = Field(default_factory=list)
    tool_calls: list[dict] = Field(default_factory=list)
    execution_time_ms: int
    usage: UsageSummary
    rag: RagMetadataResponse
