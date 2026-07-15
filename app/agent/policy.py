import json
import time

from app.agent.errors import AgentError
from app.agent.models import ToolCall


LOCAL_INTENT_KEYWORDS = (
    "hujjat",
    "document",
    "conversation",
    "chat history",
    "xabarlar",
    "history",
    "system info",
    "local system",
    "cpu",
    "ram",
    "metadata",
    "excerpt",
)


class ToolPolicy:
    def __init__(self, settings, registry) -> None:
        self._settings = settings
        self._registry = registry

    def should_use_tools(self, *, message: str, use_tools: bool | None) -> bool:
        if use_tools is False:
            return False
        if not self._settings.tools_enabled:
            if use_tools:
                raise AgentError(403, "TOOLS_DISABLED", "Tool calling hozir o'chirilgan.")
            return False
        if use_tools is True:
            return True
        if not self._settings.agent_require_explicit_tool_intent:
            return self._settings.tools_enabled
        lowered = message.lower()
        return any(keyword in lowered for keyword in LOCAL_INTENT_KEYWORDS)

    def validate_call(
        self,
        *,
        call: ToolCall,
        iteration: int,
        call_count: int,
        deadline: float,
    ) -> object:
        if not self._settings.tools_enabled:
            raise AgentError(403, "TOOLS_DISABLED", "Tool calling hozir o'chirilgan.")
        if iteration > self._settings.agent_max_iterations:
            raise AgentError(422, "AGENT_ITERATION_LIMIT", "Agent iteration limiti tugadi.")
        if call_count >= self._settings.agent_max_tool_calls:
            raise AgentError(422, "AGENT_TOOL_CALL_LIMIT", "Tool call limiti tugadi.")
        if time.monotonic() >= deadline:
            raise AgentError(504, "AGENT_TOTAL_TIMEOUT", "Agent total timeoutga yetdi.")
        serialized = json.dumps(call.arguments, ensure_ascii=False, allow_nan=False)
        if len(serialized) > self._settings.agent_max_argument_chars:
            raise AgentError(422, "TOOL_ARGUMENTS_TOO_LARGE", "Tool argumentlari limitdan oshdi.")
        return self._registry.get(call.name)

