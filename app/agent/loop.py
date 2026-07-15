import asyncio
import time

from app.agent.errors import AgentError
from app.agent.executor import ToolExecutor
from app.agent.helpers import remaining_seconds, safe_truncate
from app.agent.models import AgentLoopResult, ToolCallSummary, ToolResult
from app.agent.parser import parse_agent_response
from app.agent.prompt import TOOL_AGENT_SYSTEM_PROMPT, build_agent_messages, render_tool_definitions


class AgentLoop:
    def __init__(self, settings, registry, policy, executor: ToolExecutor | None = None) -> None:
        self._settings = settings
        self._registry = registry
        self._policy = policy
        self._executor = executor or ToolExecutor(settings)

    async def run(
        self,
        *,
        user_message: str,
        history: list[dict[str, str]],
        context_text: str | None,
        max_input_chars: int,
        ollama_call,
    ) -> AgentLoopResult:
        deadline = time.monotonic() + self._settings.agent_total_timeout_seconds
        call_count = 0
        prompt_tokens_total = 0
        completion_tokens_total = 0
        tool_results: list[ToolResult] = []
        tool_summaries: list[ToolCallSummary] = []
        tool_definitions_text = render_tool_definitions(self._registry.definitions())
        final_context_included = False

        for iteration in range(1, self._settings.agent_max_iterations + 1):
            remaining = remaining_seconds(deadline)
            if remaining <= 0:
                raise AgentError(504, "AGENT_TOTAL_TIMEOUT", "Agent total timeoutga yetdi.")
            messages, included_context = build_agent_messages(
                system_prompt=TOOL_AGENT_SYSTEM_PROMPT,
                user_message=user_message,
                history=history,
                tool_definitions_text=tool_definitions_text,
                tool_results=tool_results,
                context_text=context_text,
                max_chars=max_input_chars,
            )
            final_context_included = included_context
            try:
                result = await asyncio.wait_for(ollama_call(messages), timeout=remaining)
            except TimeoutError as exc:
                raise AgentError(504, "AGENT_TOTAL_TIMEOUT", "Agent total timeoutga yetdi.") from exc
            prompt_tokens_total += result.usage.prompt_tokens or 0
            completion_tokens_total += result.usage.completion_tokens or 0
            response_type, payload = parse_agent_response(
                result.content,
                max_calls=self._settings.agent_max_tool_calls,
            )
            if response_type == "final":
                return AgentLoopResult(
                    answer=payload,
                    tool_calls=tool_summaries,
                    iterations=iteration,
                    prompt_tokens=prompt_tokens_total,
                    completion_tokens=completion_tokens_total,
                    rag_context_included=final_context_included,
                )

            if iteration == self._settings.agent_max_iterations:
                raise AgentError(422, "AGENT_ITERATION_LIMIT", "Agent iteration limiti tugadi.")
            if call_count + len(payload) > self._settings.agent_max_tool_calls:
                raise AgentError(422, "AGENT_TOOL_CALL_LIMIT", "Tool call limiti tugadi.")
            for call in payload:
                tool = self._policy.validate_call(
                    call=call,
                    iteration=iteration,
                    call_count=call_count,
                    deadline=deadline,
                )
                tool_result = await self._executor.execute(tool=tool, call=call, iteration=iteration, deadline=deadline)
                remaining = self._settings.agent_max_tool_result_chars - sum(len(item.content) for item in tool_results)
                if remaining < len(tool_result.content):
                    content, _ = safe_truncate(tool_result.content, max(0, remaining))
                    tool_result = ToolResult(
                        call_id=tool_result.call_id,
                        tool_name=tool_result.tool_name,
                        ok=tool_result.ok,
                        content=content,
                        error_code=tool_result.error_code,
                        truncated=True,
                        execution_time_ms=tool_result.execution_time_ms,
                    )
                tool_results.append(tool_result)
                tool_summaries.append(
                    ToolCallSummary(
                        id=call.id,
                        name=call.name,
                        ok=tool_result.ok,
                        execution_time_ms=tool_result.execution_time_ms,
                        iteration=iteration,
                        error_code=tool_result.error_code,
                    )
                )
                call_count += 1
                if remaining_seconds(deadline) <= 0:
                    raise AgentError(504, "AGENT_TOTAL_TIMEOUT", "Agent total timeoutga yetdi.")
        raise AgentError(422, "AGENT_ITERATION_LIMIT", "Agent iteration limiti tugadi.")
