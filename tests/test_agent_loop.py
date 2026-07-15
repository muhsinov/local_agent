import asyncio
import time

import pytest

import app.agent.loop as loop_module
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
        self.definition = ToolDefinition(name="list_documents", description="x", input_schema={}, read_only=True, timeout_seconds=1)

    def execute(self, arguments, settings) -> str:
        return '{"items":[]}'


async def _ollama_final(messages):
    return OllamaChatResult(content='{"type":"final","answer":"done"}', usage=OllamaUsage(prompt_tokens=1, completion_tokens=1))


def _ollama_tool_then_final():
    calls = [
        OllamaChatResult(content='{"type":"tool_call","calls":[{"id":"call_1","name":"list_documents","arguments":{}}]}', usage=OllamaUsage(prompt_tokens=1, completion_tokens=1)),
        OllamaChatResult(content='{"type":"final","answer":"done"}', usage=OllamaUsage(prompt_tokens=1, completion_tokens=1)),
    ]

    async def inner(messages):
        return calls.pop(0)

    return inner


def test_agent_loop_returns_final_on_first_iteration(tmp_path) -> None:
    settings = build_settings(tmp_path)
    registry = ToolRegistry()
    registry.register(_Tool())
    loop = AgentLoop(settings, registry, ToolPolicy(settings, registry), ToolExecutor(settings))
    result = asyncio.run(loop.run(user_message="savol", history=[], context_text=None, max_input_chars=5000, ollama_call=_ollama_final))
    assert result.answer == "done"


def test_agent_loop_executes_tool_then_final(tmp_path) -> None:
    settings = build_settings(tmp_path)
    registry = ToolRegistry()
    registry.register(_Tool())
    loop = AgentLoop(settings, registry, ToolPolicy(settings, registry), ToolExecutor(settings))
    result = asyncio.run(loop.run(user_message="hujjatlarim", history=[], context_text=None, max_input_chars=5000, ollama_call=_ollama_tool_then_final()))
    assert result.answer == "done"
    assert result.tool_calls[0].name == "list_documents"


def test_agent_loop_limits_ollama_call_by_remaining_deadline(tmp_path) -> None:
    settings = build_settings(tmp_path)
    registry = ToolRegistry()
    registry.register(_Tool())
    loop = AgentLoop(settings, registry, ToolPolicy(settings, registry), ToolExecutor(settings))

    async def slow_ollama(messages):
        await asyncio.sleep(0.05)
        return OllamaChatResult(content='{"type":"final","answer":"done"}', usage=OllamaUsage(prompt_tokens=1, completion_tokens=1))

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(loop_module, "remaining_seconds", lambda deadline: 0.01)
    try:
        with pytest.raises(AgentError) as exc_info:
            asyncio.run(loop.run(user_message="savol", history=[], context_text=None, max_input_chars=5000, ollama_call=slow_ollama))
    finally:
        monkeypatch.undo()

    assert exc_info.value.code == "AGENT_TOTAL_TIMEOUT"


def test_agent_loop_rejects_tool_call_on_last_iteration(tmp_path) -> None:
    called = False

    class CountingTool(_Tool):
        def execute(self, arguments, settings) -> str:
            nonlocal called
            called = True
            return '{"items":[]}'

    settings = build_settings(tmp_path, AGENT_MAX_ITERATIONS=1, AGENT_MAX_TOOL_CALLS=1)
    registry = ToolRegistry()
    registry.register(CountingTool())
    loop = AgentLoop(settings, registry, ToolPolicy(settings, registry), ToolExecutor(settings))

    async def ollama_call(messages):
        return OllamaChatResult(
            content='{"type":"tool_call","calls":[{"id":"call_1","name":"list_documents","arguments":{}}]}',
            usage=OllamaUsage(prompt_tokens=1, completion_tokens=1),
        )

    with pytest.raises(AgentError) as exc_info:
        asyncio.run(loop.run(user_message="savol", history=[], context_text=None, max_input_chars=5000, ollama_call=ollama_call))

    assert exc_info.value.code == "AGENT_ITERATION_LIMIT"
    assert called is False


def test_agent_loop_accepts_final_answer_on_last_iteration(tmp_path) -> None:
    settings = build_settings(tmp_path, AGENT_MAX_ITERATIONS=1, AGENT_MAX_TOOL_CALLS=1)
    registry = ToolRegistry()
    registry.register(_Tool())
    loop = AgentLoop(settings, registry, ToolPolicy(settings, registry), ToolExecutor(settings))
    result = asyncio.run(loop.run(user_message="savol", history=[], context_text=None, max_input_chars=5000, ollama_call=_ollama_final))
    assert result.answer == "done"
    assert result.iterations == 1


def test_agent_loop_uses_safe_global_result_truncation(tmp_path) -> None:
    settings = build_settings(
        tmp_path,
        AGENT_MAX_TOOL_RESULT_CHARS=1000,
        AGENT_MAX_SINGLE_TOOL_RESULT_CHARS=2000,
        AGENT_MAX_TOOL_CALLS=2,
        AGENT_MAX_ITERATIONS=3,
    )
    registry = ToolRegistry()

    class LongTool(_Tool):
        def execute(self, arguments, settings) -> str:
            return "x" * 1500

    registry.register(LongTool())
    loop = AgentLoop(settings, registry, ToolPolicy(settings, registry), ToolExecutor(settings))
    captured_messages: list[list[dict[str, str]]] = []
    calls = [
        OllamaChatResult(
            content='{"type":"tool_call","calls":[{"id":"call_1","name":"list_documents","arguments":{}}]}',
            usage=OllamaUsage(prompt_tokens=1, completion_tokens=1),
        ),
        OllamaChatResult(content='{"type":"final","answer":"done"}', usage=OllamaUsage(prompt_tokens=1, completion_tokens=1)),
    ]

    async def ollama_call(messages):
        captured_messages.append(messages)
        return calls.pop(0)

    result = asyncio.run(loop.run(user_message="savol", history=[], context_text=None, max_input_chars=5000, ollama_call=ollama_call))
    assert result.tool_calls[0].ok is True
    tool_prompt = next(message["content"] for message in captured_messages[1] if message["content"].startswith("<tool_results>"))
    assert tool_prompt.endswith("</tool_result>\n</tool_results>")
    assert "...(truncated)" in tool_prompt


def test_agent_loop_raises_total_timeout_before_waiting_with_expired_deadline(monkeypatch, tmp_path) -> None:
    settings = build_settings(tmp_path)
    registry = ToolRegistry()
    registry.register(_Tool())
    loop = AgentLoop(settings, registry, ToolPolicy(settings, registry), ToolExecutor(settings))
    monkeypatch.setattr(loop_module, "remaining_seconds", lambda deadline: 0.0)

    async def ollama_call(messages):
        raise AssertionError("ollama should not be called")

    with pytest.raises(AgentError) as exc_info:
        asyncio.run(loop.run(user_message="savol", history=[], context_text=None, max_input_chars=5000, ollama_call=ollama_call))

    assert exc_info.value.code == "AGENT_TOTAL_TIMEOUT"
