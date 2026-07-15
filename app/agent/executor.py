import asyncio
import json
from time import perf_counter

from pydantic import ValidationError

from app.agent.errors import AgentError
from app.agent.helpers import remaining_seconds, safe_truncate
from app.agent.models import ToolResult
from app.agent.tool_operation_coordinator import ToolOperationCoordinator
from app.services.audit_service import write_audit_log
from app.tools.base import ReadOnlyTool


class ToolExecutor:
    def __init__(self, settings, coordinator: ToolOperationCoordinator | None = None) -> None:
        self._settings = settings
        self._coordinator = coordinator or ToolOperationCoordinator()

    async def execute(self, *, tool, call, iteration: int, deadline: float) -> ToolResult:
        started = perf_counter()
        result: ToolResult | None = None
        try:
            serialized = json.dumps(call.arguments, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as exc:
            result = self._error_result(call.id, tool.definition.name, "TOOL_ARGUMENTS_INVALID", started)
            return self._finalize(result, iteration)
        if len(serialized) > self._settings.agent_max_argument_chars:
            result = self._error_result(call.id, tool.definition.name, "TOOL_ARGUMENTS_TOO_LARGE", started)
            return self._finalize(result, iteration)
        try:
            validated = tool.input_model.model_validate(call.arguments)
        except ValidationError:
            result = self._error_result(call.id, tool.definition.name, "TOOL_ARGUMENTS_INVALID", started)
            return self._finalize(result, iteration)

        try:
            timeout_seconds = min(
                self._settings.agent_tool_timeout_seconds,
                tool.definition.timeout_seconds,
                remaining_seconds(deadline),
            )
            if timeout_seconds <= 0:
                raise AgentError(504, "AGENT_TOTAL_TIMEOUT", "Agent total timeoutga yetdi.")
            execute_async = getattr(type(tool), "execute_async", None)
            if execute_async is not None and execute_async is not ReadOnlyTool.execute_async:
                content = await asyncio.wait_for(tool.execute_async(validated, self._settings), timeout=timeout_seconds)
            else:
                outcome = await self._coordinator.run(
                    tool.execute,
                    validated,
                    self._settings,
                    timeout_seconds=timeout_seconds,
                )
                if outcome.timed_out:
                    result = self._error_result(call.id, tool.definition.name, "TOOL_EXECUTION_TIMEOUT", started)
                    return self._finalize(result, iteration)
                content = outcome.value
            truncated_content, truncated = safe_truncate(content, self._settings.agent_max_single_tool_result_chars)
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
            result = self._error_result(call.id, tool.definition.name, "TOOL_EXECUTION_TIMEOUT", started)
        except asyncio.CancelledError:
            raise
        except AgentError:
            raise
        except Exception:
            result = self._error_result(call.id, tool.definition.name, "TOOL_EXECUTION_ERROR", started)
        return self._finalize(result, iteration)

    def _finalize(self, result: ToolResult, iteration: int) -> ToolResult:
        try:
            write_audit_log(
                self._settings,
                action="tool_execute",
                status="ok" if result.ok else "error",
                arguments={
                    "tool_name": result.tool_name,
                    "success": result.ok,
                    "result_count": len(result.content),
                    "execution_time_ms": result.execution_time_ms,
                    "truncated": result.truncated,
                    "iteration": iteration,
                    "error_code": result.error_code,
                },
                execution_time_ms=result.execution_time_ms,
            )
        except Exception:
            pass
        return result

    def _error_result(self, call_id: str, tool_name: str, code: str, started: float) -> ToolResult:
        return ToolResult(
            call_id=call_id,
            tool_name=tool_name,
            ok=False,
            content="" if not self._settings.agent_include_tool_errors_in_prompt else code,
            error_code=code,
            truncated=False,
            execution_time_ms=int((perf_counter() - started) * 1000),
        )
