import re

from app.agent.errors import AgentError
from app.agent.models import ToolDefinition


TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, object] = {}

    def register(self, tool: object) -> None:
        definition: ToolDefinition = tool.definition
        if not TOOL_NAME_PATTERN.fullmatch(definition.name):
            raise AgentError(500, "TOOL_POLICY_DENIED", "Tool nomi noto'g'ri.")
        if not definition.read_only:
            raise AgentError(500, "TOOL_POLICY_DENIED", "Write tool ruxsat etilmagan.")
        if definition.name in self._tools:
            raise AgentError(500, "TOOL_POLICY_DENIED", "Duplicate tool nomi ruxsat etilmagan.")
        self._tools[definition.name] = tool

    def get(self, name: str) -> object:
        tool = self._tools.get(name)
        if tool is None:
            raise AgentError(404, "TOOL_NOT_FOUND", "So'ralgan tool topilmadi.")
        return tool

    def definitions(self) -> list[ToolDefinition]:
        return [tool.definition for tool in self._tools.values()]


def build_default_registry(settings, coordinator) -> ToolRegistry:
    from app.tools.conversation_tools import GetConversationMessagesTool, ListConversationsTool
    from app.tools.document_tools import GetDocumentExcerptTool, GetDocumentMetadataTool, ListDocumentsTool, SearchDocumentsTool
    from app.tools.system_info_tools import GetLocalSystemInfoTool

    registry = ToolRegistry()
    timeout = settings.agent_tool_timeout_seconds
    registry.register(ListDocumentsTool(timeout))
    registry.register(GetDocumentMetadataTool(timeout))
    registry.register(GetDocumentExcerptTool(timeout))
    registry.register(SearchDocumentsTool(timeout, coordinator))
    registry.register(ListConversationsTool(timeout))
    registry.register(GetConversationMessagesTool(timeout))
    registry.register(GetLocalSystemInfoTool(timeout))
    return registry
