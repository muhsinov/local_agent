import asyncio

from pydantic import BaseModel, ConfigDict

from app.agent.executor import ToolExecutor
from app.agent.models import ToolCall, ToolDefinition
from tests.conftest import build_settings


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: int


class _Tool:
    input_model = _Args

    def __init__(self) -> None:
        self.definition = ToolDefinition(name="demo_tool", description="x", input_schema={}, read_only=True, timeout_seconds=1)

    def execute(self, arguments, settings) -> str:
        return "x" * 400


def test_executor_truncates_large_result(tmp_path) -> None:
    settings = build_settings(tmp_path, AGENT_MAX_SINGLE_TOOL_RESULT_CHARS=200)
    result = asyncio.run(ToolExecutor(settings).execute(tool=_Tool(), call=ToolCall(id="1", name="demo_tool", arguments={"value": 1}), iteration=1))
    assert result.ok is True
    assert result.truncated is True


def test_executor_rejects_invalid_arguments(tmp_path) -> None:
    settings = build_settings(tmp_path)
    result = asyncio.run(ToolExecutor(settings).execute(tool=_Tool(), call=ToolCall(id="1", name="demo_tool", arguments={"bad": 1}), iteration=1))
    assert result.ok is False
    assert result.error_code == "TOOL_ARGUMENTS_INVALID"
