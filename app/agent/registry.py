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
        if definition.read_only and (definition.requires_approval or definition.write_effect):
            raise AgentError(500, "TOOL_POLICY_DENIED", "Read-only tool policy flaglari noto'g'ri.")
        if definition.write_effect and not definition.requires_approval:
            raise AgentError(500, "TOOL_POLICY_DENIED", "Write tool approval talab qilishi kerak.")
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
    from app.tools.conversation_tools import GetConversationMessagesTool, ListConversationsTool, RenameConversationTool
    from app.tools.document_tools import (
        GetDocumentExcerptTool,
        GetDocumentMetadataTool,
        ListDocumentsTool,
        RebuildVectorIndexTool,
        SearchDocumentsTool,
    )
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
    if settings.approval_allow_rename_conversation:
        registry.register(RenameConversationTool(timeout))
    if settings.approval_allow_rebuild_vector_index:
        registry.register(RebuildVectorIndexTool(timeout))
    return registry
