from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """Incoming chat request payload."""

    message: str = Field(min_length=1)
    conversation_id: int | None = Field(default=None, ge=1)

    @field_validator("message", mode="before")
    @classmethod
    def trim_message(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Message matn bo'lishi kerak.")
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Bo'sh xabar yuborib bo'lmaydi.")
        return trimmed


class UsageSummary(BaseModel):
    """Usage values returned to the frontend."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class ChatResponse(BaseModel):
    """Outgoing chat response payload."""

    conversation_id: int
    answer: str
    model: str
    sources: list[dict] = Field(default_factory=list)
    tool_calls: list[dict] = Field(default_factory=list)
    execution_time_ms: int
    usage: UsageSummary
