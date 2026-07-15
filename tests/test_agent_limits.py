import asyncio

import pytest

from app.agent.errors import AgentError
from app.agent.executor import ToolExecutor
from app.agent.loop import AgentLoop
from app.agent.models import ToolDefinition
from app.agent.policy import ToolPolicy
from app.agent.registry import ToolRegistry
from app.llm.ollama_client import OllamaChatResult, OllamaUsage
from tests.conftest import build_settings


class _Args:
    @classmethod
    def model_validate(cls, value):
        return type("Validated", (), value)()


class _Tool:
    input_model = _Args

    def __init__(self) -> None:
        self.definition = ToolDefinition(
            name="list_documents",
            description="x",
            input_schema={},
            read_only=True,
            timeout_seconds=1,
        )

    def execute(self, arguments, settings) -> str:
        return '{"items":[]}'


def _build_loop(tmp_path, **setting_overrides) -> AgentLoop:
    settings = build_settings(tmp_path, **setting_overrides)
    registry = ToolRegistry()
    registry.register(_Tool())
    return AgentLoop(settings, registry, ToolPolicy(settings, registry), ToolExecutor(settings))


def test_agent_loop_enforces_iteration_limit(tmp_path) -> None:
    loop = _build_loop(tmp_path, AGENT_MAX_ITERATIONS=1, AGENT_MAX_TOOL_CALLS=1)

    async def ollama_call(messages):
        return OllamaChatResult(
            content='{"type":"tool_call","calls":[{"id":"call_1","name":"list_documents","arguments":{}}]}',
            usage=OllamaUsage(prompt_tokens=1, completion_tokens=1),
        )

    with pytest.raises(AgentError) as exc_info:
        asyncio.run(loop.run(user_message="hujjatlarim", history=[], context_text=None, max_input_chars=5000, ollama_call=ollama_call))

    assert exc_info.value.code == "AGENT_ITERATION_LIMIT"


def test_agent_loop_enforces_total_tool_call_limit(tmp_path) -> None:
    loop = _build_loop(tmp_path, AGENT_MAX_ITERATIONS=5, AGENT_MAX_TOOL_CALLS=1)
    responses = [
        OllamaChatResult(
            content='{"type":"tool_call","calls":[{"id":"call_1","name":"list_documents","arguments":{}}]}',
            usage=OllamaUsage(prompt_tokens=1, completion_tokens=1),
        ),
        OllamaChatResult(
            content='{"type":"tool_call","calls":[{"id":"call_2","name":"list_documents","arguments":{}}]}',
            usage=OllamaUsage(prompt_tokens=1, completion_tokens=1),
        ),
    ]

    async def ollama_call(messages):
        return responses.pop(0)

    with pytest.raises(AgentError) as exc_info:
        asyncio.run(loop.run(user_message="hujjatlarim", history=[], context_text=None, max_input_chars=5000, ollama_call=ollama_call))

    assert exc_info.value.code == "AGENT_TOOL_CALL_LIMIT"
