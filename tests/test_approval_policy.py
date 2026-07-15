import asyncio
import time

import pytest

from app.agent.errors import AgentError
from app.agent.executor import ToolExecutor
from app.agent.loop import AgentLoop
from app.agent.models import ToolCall, ToolDefinition
from app.agent.policy import ToolPolicy
from app.agent.registry import ToolRegistry
from tests.conftest import build_settings


class _Args:
    @classmethod
    def model_validate(cls, value):
        return type("Validated", (), value)()


class _ReadTool:
    input_model = _Args

    def __init__(self) -> None:
        self.definition = ToolDefinition(name="list_documents", description="x", input_schema={}, read_only=True, timeout_seconds=1)

    def execute(self, arguments, settings) -> str:
        return "{}"


class _WriteTool:
    input_model = _Args

    def __init__(self) -> None:
        self.definition = ToolDefinition(
            name="rename_conversation",
            description="x",
            input_schema={},
            read_only=False,
            timeout_seconds=1,
            requires_approval=True,
            write_effect=True,
        )

    def build_safe_summary(self, arguments) -> str:
        return "rename"


def test_direct_executor_rejects_write_tool(tmp_path) -> None:
    settings = build_settings(tmp_path)
    with pytest.raises(AgentError) as exc_info:
        asyncio.run(
            ToolExecutor(settings).execute(
                tool=_WriteTool(),
                call=ToolCall(id="call_1", name="rename_conversation", arguments={}),
                iteration=1,
                deadline=time.monotonic() + 5,
            )
        )
    assert exc_info.value.code == "TOOL_APPROVAL_REQUIRED"


def test_agent_loop_returns_approval_required_for_write_tool(tmp_path) -> None:
    settings = build_settings(tmp_path, TOOLS_ENABLED=True)
    registry = ToolRegistry()
    registry.register(_WriteTool())
    loop = AgentLoop(settings, registry, ToolPolicy(settings, registry), ToolExecutor(settings))

    async def ollama_call(messages):
        return type(
            "Result",
            (),
            {
                "content": '{"type":"tool_call","calls":[{"id":"call_1","name":"rename_conversation","arguments":{}}]}',
                "usage": type("Usage", (), {"prompt_tokens": 1, "completion_tokens": 1})(),
            },
        )()

    result = asyncio.run(loop.run(user_message="nomini o'zgartir", history=[], context_text=None, max_input_chars=4000, ollama_call=ollama_call))
    assert result.approval_required is not None
    assert result.approval_required.tool_call.name == "rename_conversation"


def test_agent_loop_rejects_mixed_read_and_write_calls(tmp_path) -> None:
    settings = build_settings(tmp_path, TOOLS_ENABLED=True)
    registry = ToolRegistry()
    registry.register(_ReadTool())
    registry.register(_WriteTool())
    loop = AgentLoop(settings, registry, ToolPolicy(settings, registry), ToolExecutor(settings))

    async def ollama_call(messages):
        return type(
            "Result",
            (),
            {
                "content": '{"type":"tool_call","calls":[{"id":"call_1","name":"list_documents","arguments":{}},{"id":"call_2","name":"rename_conversation","arguments":{}}]}',
                "usage": type("Usage", (), {"prompt_tokens": 1, "completion_tokens": 1})(),
            },
        )()

    with pytest.raises(AgentError) as exc_info:
        asyncio.run(loop.run(user_message="ikkalasini qil", history=[], context_text=None, max_input_chars=4000, ollama_call=ollama_call))
    assert exc_info.value.code == "MULTIPLE_APPROVAL_ACTIONS_NOT_ALLOWED"
