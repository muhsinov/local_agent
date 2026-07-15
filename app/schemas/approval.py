from pydantic import BaseModel


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
