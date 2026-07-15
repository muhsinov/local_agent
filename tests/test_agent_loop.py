import asyncio

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
        OllamaChatResult(content='{"type":"tool_call","calls":[{"id":"1","name":"list_documents","arguments":{}}]}', usage=OllamaUsage(prompt_tokens=1, completion_tokens=1)),
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
