import pytest

from app.agent.errors import AgentError
from app.agent.models import ToolCall, ToolDefinition
from app.agent.policy import ToolPolicy
from app.agent.registry import ToolRegistry
from tests.conftest import build_settings


class _Tool:
    def __init__(self) -> None:
        self.definition = ToolDefinition(name="list_documents", description="x", input_schema={}, read_only=True, timeout_seconds=1)


def _policy(tmp_path, **overrides):
    settings = build_settings(tmp_path, **overrides)
    registry = ToolRegistry()
    registry.register(_Tool())
    return ToolPolicy(settings, registry)


def test_policy_requires_explicit_intent(tmp_path) -> None:
    policy = _policy(tmp_path)
    assert policy.should_use_tools(message="salom", use_tools=None) is False
    assert policy.should_use_tools(message="hujjatlarimdan top", use_tools=None) is True


def test_policy_rejects_disabled_tools_when_forced(tmp_path) -> None:
    policy = _policy(tmp_path, TOOLS_ENABLED=False)
    with pytest.raises(AgentError) as exc:
        policy.should_use_tools(message="hujjat", use_tools=True)
    assert exc.value.code == "TOOLS_DISABLED"


def test_policy_rejects_large_arguments(tmp_path) -> None:
    policy = _policy(tmp_path, AGENT_MAX_ARGUMENT_CHARS=100)
    with pytest.raises(AgentError) as exc:
        policy.validate_call(
            call=ToolCall(id="1", name="list_documents", arguments={"x": "a" * 150}),
            iteration=1,
            call_count=0,
            deadline=9999999999,
        )
    assert exc.value.code == "TOOL_ARGUMENTS_TOO_LARGE"
