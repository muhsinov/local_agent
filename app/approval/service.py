import json
import uuid

from app.agent.models import ApprovalRequired
from app.approval.errors import ApprovalError
from app.approval.policy import ensure_approvals_enabled
from app.approval.repository import create_approval, expire_pending_approvals, get_approval, mark_rejected, recover_stale_executions
from app.approval.security import canonicalize_arguments, compare_hash, generate_approval_nonce, hash_text, is_local_origin
from app.services.audit_service import write_audit_log


class ApprovalService:
    def __init__(self, settings) -> None:
        self._settings = settings

    def cleanup_expired(self, active_approval_ids: set[str] | None = None) -> int:
        expire_pending_approvals(self._settings)
        return recover_stale_executions(self._settings, active_approval_ids)

    def create_pending(
        self,
        *,
        approval_required: ApprovalRequired,
        conversation_id: int | None,
        original_user_message: str,
        use_rag: bool,
        document_ids: list[int] | None,
    ) -> tuple[object, str]:
        ensure_approvals_enabled(self._settings)
        nonce = generate_approval_nonce(self._settings.approval_nonce_bytes)
        arguments_json = canonicalize_arguments(approval_required.tool_call.arguments)
        approval = create_approval(
            self._settings,
            approval_id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            tool_call_id=approval_required.tool_call.id,
            tool_name=approval_required.tool_call.name,
            arguments_json=arguments_json,
            arguments_sha256=hash_text(arguments_json),
            nonce_sha256=hash_text(nonce),
            original_user_message=original_user_message,
            use_rag=use_rag,
            document_ids_json=json.dumps(document_ids) if document_ids is not None else None,
            safe_summary=approval_required.safe_summary,
            expiry_seconds=self._settings.approval_expiry_seconds,
            max_pending=self._settings.approval_max_pending,
        )
        write_audit_log(
            self._settings,
            action="approval_create",
            status="pending",
            arguments={
                "approval_id": approval.id,
                "tool_name": approval.tool_name,
                "conversation_id": conversation_id,
                "status": "pending",
                "argument_hash_prefix": approval.arguments_sha256[:12],
            },
        )
        return approval, nonce

    def get_public(self, approval_id: str, active_approval_ids: set[str] | None = None) -> object:
        expire_pending_approvals(self._settings)
        recover_stale_executions(self._settings, active_approval_ids)
        approval = get_approval(self._settings, approval_id)
        if approval is None:
            raise ApprovalError(404, "APPROVAL_NOT_FOUND", "Approval topilmadi.")
        return approval

    def validate_nonce_and_origin(
        self,
        approval_id: str,
        nonce: str,
        origin_or_referer: str | None,
        active_approval_ids: set[str] | None = None,
    ) -> object:
        ensure_approvals_enabled(self._settings)
        expire_pending_approvals(self._settings)
        recover_stale_executions(self._settings, active_approval_ids)
        approval = get_approval(self._settings, approval_id)
        if approval is None:
            raise ApprovalError(404, "APPROVAL_NOT_FOUND", "Approval topilmadi.")
        if self._settings.approval_require_local_origin and not is_local_origin(origin_or_referer, self._settings.port):
            raise ApprovalError(403, "APPROVAL_ORIGIN_DENIED", "Approval origin ruxsat etilmagan.")
        if not compare_hash(nonce, approval.nonce_sha256):
            raise ApprovalError(403, "APPROVAL_INVALID_NONCE", "Approval nonce noto'g'ri.")
        return approval

    def reject(self, approval_id: str, nonce: str, origin_or_referer: str | None, active_approval_ids: set[str] | None = None) -> object:
        approval = self.validate_nonce_and_origin(approval_id, nonce, origin_or_referer, active_approval_ids)
        affected = mark_rejected(self._settings, approval_id)
        if affected != 1:
            refreshed = get_approval(self._settings, approval_id)
            if refreshed is None:
                raise ApprovalError(404, "APPROVAL_NOT_FOUND", "Approval topilmadi.")
            if refreshed.status == "expired":
                raise ApprovalError(409, "APPROVAL_EXPIRED", "Approval muddati tugagan.")
            if refreshed.status in {"executing", "executed", "rejected", "failed"}:
                raise ApprovalError(409, "APPROVAL_ALREADY_USED", "Approval avval ishlatilgan.")
            raise ApprovalError(409, "APPROVAL_NOT_PENDING", "Approval pending holatda emas.")
        write_audit_log(
            self._settings,
            action="approval_decision",
            status="rejected",
            arguments={
                "approval_id": approval.id,
                "tool_name": approval.tool_name,
                "conversation_id": approval.conversation_id,
                "status": "rejected",
                "argument_hash_prefix": approval.arguments_sha256[:12],
            },
        )
        return get_approval(self._settings, approval_id)
