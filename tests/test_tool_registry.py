import pytest

from app.agent.errors import AgentError
from app.agent.models import ToolDefinition
from app.agent.registry import ToolRegistry


class _Tool:
    def __init__(self, name: str, read_only: bool = True, requires_approval: bool = False, write_effect: bool = False) -> None:
        self.definition = ToolDefinition(
            name=name,
            description="x",
            input_schema={},
            read_only=read_only,
            timeout_seconds=1,
            requires_approval=requires_approval,
            write_effect=write_effect,
        )


def test_registry_rejects_duplicate_tool() -> None:
    registry = ToolRegistry()
    registry.register(_Tool("list_documents"))
    with pytest.raises(AgentError):
        registry.register(_Tool("list_documents"))


def test_registry_rejects_invalid_name() -> None:
    registry = ToolRegistry()
    with pytest.raises(AgentError):
        registry.register(_Tool("BadName"))


def test_registry_allows_write_tool_when_approval_is_required() -> None:
    registry = ToolRegistry()
    registry.register(_Tool("write_tool", read_only=False, requires_approval=True, write_effect=True))
