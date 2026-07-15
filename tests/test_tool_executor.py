import asyncio
import threading
import time

import pytest
from pydantic import BaseModel, ConfigDict

from app.agent.executor import ToolExecutor
from app.agent.errors import AgentError
from app.agent.models import ToolCall, ToolDefinition
from app.agent.tool_operation_coordinator import ToolOperationCoordinator, ToolOperationOutcome
from tests.conftest import build_settings


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: int


class _Tool:
    input_model = _Args

    def __init__(self, *, timeout_seconds: int = 1) -> None:
        self.definition = ToolDefinition(name="demo_tool", description="x", input_schema={}, read_only=True, timeout_seconds=timeout_seconds)

    def execute(self, arguments, settings) -> str:
        return "x" * 400


def test_executor_truncates_large_result(tmp_path) -> None:
    settings = build_settings(tmp_path, AGENT_MAX_SINGLE_TOOL_RESULT_CHARS=200)
    deadline = time.monotonic() + 30
    result = asyncio.run(ToolExecutor(settings).execute(tool=_Tool(), call=ToolCall(id="1", name="demo_tool", arguments={"value": 1}), iteration=1, deadline=deadline))
    assert result.ok is True
    assert result.truncated is True


def test_executor_rejects_invalid_arguments(tmp_path) -> None:
    settings = build_settings(tmp_path)
    deadline = time.monotonic() + 30
    result = asyncio.run(ToolExecutor(settings).execute(tool=_Tool(), call=ToolCall(id="1", name="demo_tool", arguments={"bad": 1}), iteration=1, deadline=deadline))
    assert result.ok is False
    assert result.error_code == "TOOL_ARGUMENTS_INVALID"


def test_executor_writes_timeout_audit(monkeypatch, tmp_path) -> None:
    started = threading.Event()
    release = threading.Event()
    audit_calls: list[dict] = []

    class SlowTool(_Tool):
        def execute(self, arguments, settings) -> str:
            started.set()
            release.wait(timeout=1)
            return "done"

    def fake_audit(settings, *, action, status, arguments, execution_time_ms=None) -> None:
        audit_calls.append({"action": action, "status": status, "arguments": arguments})

    monkeypatch.setattr("app.agent.executor.write_audit_log", fake_audit)
    settings = build_settings(tmp_path, AGENT_TOOL_TIMEOUT_SECONDS=1)
    deadline = time.monotonic() + 0.02

    async def scenario() -> None:
        executor = ToolExecutor(settings, ToolOperationCoordinator())
        result = await executor.execute(
            tool=SlowTool(timeout_seconds=5),
            call=ToolCall(id="1", name="demo_tool", arguments={"value": 1}),
            iteration=1,
            deadline=deadline,
        )
        assert result.error_code == "TOOL_EXECUTION_TIMEOUT"
        release.set()
        await executor._coordinator.shutdown(timeout_seconds=0.2)

    asyncio.run(scenario())
    assert started.is_set() is True
    assert audit_calls[-1]["arguments"]["error_code"] == "TOOL_EXECUTION_TIMEOUT"


def test_executor_writes_invalid_argument_audit(monkeypatch, tmp_path) -> None:
    audit_calls: list[dict] = []

    def fake_audit(settings, *, action, status, arguments, execution_time_ms=None) -> None:
        audit_calls.append({"action": action, "status": status, "arguments": arguments})

    monkeypatch.setattr("app.agent.executor.write_audit_log", fake_audit)
    settings = build_settings(tmp_path)
    deadline = time.monotonic() + 30
    result = asyncio.run(
        ToolExecutor(settings).execute(
            tool=_Tool(),
            call=ToolCall(id="1", name="demo_tool", arguments={"bad": 1}),
            iteration=2,
            deadline=deadline,
        )
    )
    assert result.error_code == "TOOL_ARGUMENTS_INVALID"
    assert audit_calls[-1]["arguments"]["iteration"] == 2
    assert audit_calls[-1]["arguments"]["error_code"] == "TOOL_ARGUMENTS_INVALID"


def test_executor_writes_oversized_argument_audit(monkeypatch, tmp_path) -> None:
    audit_calls: list[dict] = []

    class _LargeArgs(BaseModel):
        model_config = ConfigDict(extra="forbid")
        value: str

    class LargeTool:
        input_model = _LargeArgs

        def __init__(self) -> None:
            self.definition = ToolDefinition(name="demo_tool", description="x", input_schema={}, read_only=True, timeout_seconds=1)

        def execute(self, arguments, settings) -> str:
            return "ok"

    def fake_audit(settings, *, action, status, arguments, execution_time_ms=None) -> None:
        audit_calls.append(arguments)

    monkeypatch.setattr("app.agent.executor.write_audit_log", fake_audit)
    settings = build_settings(tmp_path, AGENT_MAX_ARGUMENT_CHARS=100)
    deadline = time.monotonic() + 30
    result = asyncio.run(
        ToolExecutor(settings).execute(
            tool=LargeTool(),
            call=ToolCall(id="1", name="demo_tool", arguments={"value": "a" * 200}),
            iteration=3,
            deadline=deadline,
        )
    )
    assert result.error_code == "TOOL_ARGUMENTS_TOO_LARGE"
    assert audit_calls[-1]["error_code"] == "TOOL_ARGUMENTS_TOO_LARGE"


def test_executor_uses_remaining_deadline_as_effective_timeout(tmp_path) -> None:
    captured: dict[str, float] = {}

    class FakeCoordinator:
        async def run(self, function, *args, timeout_seconds: float, **kwargs):
            captured["timeout_seconds"] = timeout_seconds
            return ToolOperationOutcome(value="ok")

    settings = build_settings(tmp_path, AGENT_TOOL_TIMEOUT_SECONDS=5)
    deadline = time.monotonic() + 0.05
    result = asyncio.run(
        ToolExecutor(settings, FakeCoordinator()).execute(
            tool=_Tool(timeout_seconds=10),
            call=ToolCall(id="1", name="demo_tool", arguments={"value": 1}),
            iteration=1,
            deadline=deadline,
        )
    )
    assert result.ok is True
    assert 0 < captured["timeout_seconds"] <= 0.06


def test_executor_does_not_start_tool_after_deadline(tmp_path) -> None:
    called = False

    class GuardTool(_Tool):
        def execute(self, arguments, settings) -> str:
            nonlocal called
            called = True
            return "nope"

    settings = build_settings(tmp_path)

    async def scenario() -> None:
        with pytest.raises(AgentError) as exc_info:
            await ToolExecutor(settings).execute(
                tool=GuardTool(),
                call=ToolCall(id="1", name="demo_tool", arguments={"value": 1}),
                iteration=1,
                deadline=time.monotonic(),
            )
        assert exc_info.value.code == "AGENT_TOTAL_TIMEOUT"

    asyncio.run(scenario())
    assert called is False


def test_cancellation_does_not_release_sync_tool_slot_early(tmp_path) -> None:
    started = threading.Event()
    release = threading.Event()

    class SlowTool(_Tool):
        def execute(self, arguments, settings) -> str:
            started.set()
            release.wait(timeout=1)
            return "done"

    async def scenario() -> None:
        settings = build_settings(tmp_path, AGENT_TOOL_TIMEOUT_SECONDS=1)
        coordinator = ToolOperationCoordinator()
        executor = ToolExecutor(settings, coordinator)
        deadline = time.monotonic() + 1
        first = asyncio.create_task(
            executor.execute(
                tool=SlowTool(timeout_seconds=5),
                call=ToolCall(id="1", name="demo_tool", arguments={"value": 1}),
                iteration=1,
                deadline=deadline,
            )
        )
        while not started.is_set():
            await asyncio.sleep(0.001)
        first.cancel()
        first.cancel()
        for _ in range(2):
            try:
                await first
            except asyncio.CancelledError:
                pass
        blocked = await executor.execute(
            tool=SlowTool(timeout_seconds=5),
            call=ToolCall(id="2", name="demo_tool", arguments={"value": 1}),
            iteration=1,
            deadline=time.monotonic() + 0.02,
        )
        assert blocked.error_code == "TOOL_EXECUTION_TIMEOUT"
        release.set()
        await coordinator.shutdown(timeout_seconds=0.2)
        result = await executor.execute(
            tool=SlowTool(timeout_seconds=5),
            call=ToolCall(id="3", name="demo_tool", arguments={"value": 1}),
            iteration=1,
            deadline=time.monotonic() + 0.2,
        )
        assert result.ok is True

    asyncio.run(scenario())
