from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict
    read_only: bool
    timeout_seconds: int


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    tool_name: str
    ok: bool
    content: str
    error_code: str | None
    truncated: bool
    execution_time_ms: int


@dataclass(frozen=True)
class ToolCallSummary:
    id: str
    name: str
    ok: bool
    execution_time_ms: int
    iteration: int
    error_code: str | None = None


@dataclass(frozen=True)
class AgentLoopResult:
    answer: str
    tool_calls: list[ToolCallSummary] = field(default_factory=list)
    iterations: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    rag_context_included: bool = False

