import pytest

from app.agent.errors import AgentError
from app.agent.models import ToolDefinition
from app.agent.registry import ToolRegistry


class _Tool:
    def __init__(self, name: str, read_only: bool = True) -> None:
        self.definition = ToolDefinition(name=name, description="x", input_schema={}, read_only=read_only, timeout_seconds=1)


def test_registry_rejects_duplicate_tool() -> None:
    registry = ToolRegistry()
    registry.register(_Tool("list_documents"))
    with pytest.raises(AgentError):
        registry.register(_Tool("list_documents"))


def test_registry_rejects_invalid_name() -> None:
    registry = ToolRegistry()
    with pytest.raises(AgentError):
        registry.register(_Tool("BadName"))


def test_registry_rejects_write_tool() -> None:
    registry = ToolRegistry()
    with pytest.raises(AgentError):
        registry.register(_Tool("write_tool", read_only=False))
