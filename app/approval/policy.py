from app.agent.errors import AgentError


def ensure_approvals_enabled(settings) -> None:
    if not settings.approvals_enabled:
        raise AgentError(403, "APPROVALS_DISABLED", "Approval workflow hozir o'chirilgan.")
