from dataclasses import dataclass


@dataclass(frozen=True)
class ApprovalRequest:
    id: str
    conversation_id: int | None
    tool_call_id: str
    tool_name: str
    arguments_sha256: str
    status: str
    safe_summary: str
    created_at: str
    expires_at: str


@dataclass(frozen=True)
class ApprovalRecord(ApprovalRequest):
    arguments_json: str
    nonce_sha256: str
    original_user_message: str
    use_rag: bool
    document_ids_json: str | None
    executing_at: str | None
    completed_at: str | None
    error_code: str | None
    execution_result_json: str | None
    execution_deadline_at: str | None
    result_message_id: int | None
