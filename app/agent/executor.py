import asyncio
import json
from time import perf_counter

from pydantic import ValidationError

from app.agent.models import ToolResult
from app.services.audit_service import write_audit_log
from app.tools.base import ReadOnlyTool


def _safe_truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    suffix = "\n...(truncated)"
    head = max(0, limit - len(suffix))
    return f"{text[:head]}{suffix}", True


class ToolExecutor:
    def __init__(self, settings) -> None:
        self._settings = settings

    async def execute(self, *, tool, call, iteration: int) -> ToolResult:
        started = perf_counter()
        try:
            serialized = json.dumps(call.arguments, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as exc:
            return self._error_result(call.id, tool.definition.name, "TOOL_ARGUMENTS_INVALID", started, iteration)
        if len(serialized) > self._settings.agent_max_argument_chars:
            return self._error_result(call.id, tool.definition.name, "TOOL_ARGUMENTS_TOO_LARGE", started, iteration)
        try:
            validated = tool.input_model.model_validate(call.arguments)
        except ValidationError:
            return self._error_result(call.id, tool.definition.name, "TOOL_ARGUMENTS_INVALID", started, iteration)

        timeout_seconds = min(self._settings.agent_tool_timeout_seconds, tool.definition.timeout_seconds)
        try:
            execute_async = getattr(type(tool), "execute_async", None)
            if execute_async is not None and execute_async is not ReadOnlyTool.execute_async:
                content = await asyncio.wait_for(tool.execute_async(validated, self._settings), timeout=timeout_seconds)
            else:
                content = await asyncio.wait_for(
                    asyncio.to_thread(tool.execute, validated, self._settings),
                    timeout=timeout_seconds,
                )
            truncated_content, truncated = _safe_truncate(content, self._settings.agent_max_single_tool_result_chars)
            result = ToolResult(
                call_id=call.id,
                tool_name=tool.definition.name,
                ok=True,
                content=truncated_content,
                error_code=None,
                truncated=truncated,
                execution_time_ms=int((perf_counter() - started) * 1000),
            )
        except TimeoutError:
            result = self._error_result(call.id, tool.definition.name, "TOOL_EXECUTION_TIMEOUT", started, iteration)
        except Exception:
            result = self._error_result(call.id, tool.definition.name, "TOOL_EXECUTION_ERROR", started, iteration)

        write_audit_log(
            self._settings,
            action="tool_execute",
            status="ok" if result.ok else "error",
            arguments={
                "tool_name": result.tool_name,
                "result_count": len(result.content),
                "execution_time_ms": result.execution_time_ms,
                "truncated": result.truncated,
                "iteration": iteration,
                "error_code": result.error_code,
            },
            execution_time_ms=result.execution_time_ms,
        )
        return result

    def _error_result(self, call_id: str, tool_name: str, code: str, started: float, iteration: int) -> ToolResult:
        return ToolResult(
            call_id=call_id,
            tool_name=tool_name,
            ok=False,
            content="" if not self._settings.agent_include_tool_errors_in_prompt else code,
            error_code=code,
            truncated=False,
            execution_time_ms=int((perf_counter() - started) * 1000),
        )
