from app.approval.errors import ApprovalError


def ensure_approvals_enabled(settings) -> None:
    if not settings.approvals_enabled:
        raise ApprovalError(403, "APPROVALS_DISABLED", "Approval workflow hozir o'chirilgan.")
