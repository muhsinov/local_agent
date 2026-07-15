from pydantic import BaseModel, Field

from app.schemas.rag import RagMetadataResponse, RagSourceResponse


class ApprovalPendingResponse(BaseModel):
    required: bool = True
    approval_id: str
    nonce: str
    tool_name: str
    safe_summary: str
    expires_at: str


class ApprovalStatusResponse(BaseModel):
    approval_id: str
    conversation_id: int | None
    tool_name: str
    status: str
    safe_summary: str
    created_at: str
    expires_at: str
    completed_at: str | None = None
    error_code: str | None = None


class ApprovalDecisionRequest(BaseModel):
    nonce: str


class ApprovalDecisionResponse(ApprovalStatusResponse):
    answer: str | None = None
    conversation_id_result: int | None = None


class ApprovalResultResponse(BaseModel):
    approval_id: str
    status: str
    conversation_id: int | None
    answer: str | None = None
    sources: list[RagSourceResponse] = Field(default_factory=list)
    rag: RagMetadataResponse
    usage: dict[str, int | None] = Field(default_factory=lambda: {"prompt_tokens": None, "completion_tokens": None})
    error_code: str | None = None
