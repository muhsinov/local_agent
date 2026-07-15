import asyncio
import threading

import pytest

from app.agent.tool_operation_coordinator import ToolOperationCoordinator
from app.approval.operation_coordinator import ApprovalOperationCoordinator
from app.rag.operation_coordinator import VectorOperationCoordinator
from app.runtime.lifecycle import RuntimeLifecycle


def test_lifecycle_restart_requires_zero_active_requests():
    async def scenario():
        lifecycle = RuntimeLifecycle()
        assert await lifecycle.enter()
        await lifecycle.begin_drain()
        with pytest.raises(RuntimeError, match="RUNTIME_ACTIVE_DURING_START"):
            await lifecycle.start()
        await lifecycle.exit()
        await lifecycle.start()
        assert await lifecycle.enter()

    asyncio.run(scenario())


def test_queued_operations_are_rejected_after_post_lock_drain():
    async def scenario():
        tool = ToolOperationCoordinator()
        vector = VectorOperationCoordinator()
        tool_started = threading.Event()
        release = threading.Event()

        def slow_tool():
            tool_started.set()
            release.wait(timeout=1)
            return "ok"

        first = asyncio.create_task(tool.run(slow_tool, operation_deadline=asyncio.get_running_loop().time() + 1, timeout_code="TIMEOUT"))
        while not tool_started.is_set():
            await asyncio.sleep(0)
        queued = asyncio.create_task(tool.run(lambda: "queued", operation_deadline=asyncio.get_running_loop().time() + 1, timeout_code="TIMEOUT"))
        tool.begin_drain()
        release.set()
        assert (await first).value == "ok"
        assert (await queued).timeout_code == "SERVER_DRAINING"

        vector.begin_drain()
        with pytest.raises(RuntimeError, match="VECTOR_COORDINATOR_DRAINING"):
            await vector.run(lambda: "no", acquire_timeout_seconds=1)
        await tool.shutdown()
        await vector.shutdown()
        assert tool.closed and vector.closed

    asyncio.run(scenario())


def test_approval_drain_rejects_new_operations_and_consumes_failure():
    async def scenario():
        coordinator = ApprovalOperationCoordinator()
        coordinator.begin_drain()
        with pytest.raises(RuntimeError, match="APPROVAL_COORDINATOR_DRAINING"):
            await coordinator.start_or_join(approval_id="safe-id", operation_factory=lambda: asyncio.sleep(0))
        coordinator.start()
        task = await coordinator.start_or_join(approval_id="safe-id", operation_factory=lambda: asyncio.sleep(0, result="ok"))
        assert await task == "ok"
        await asyncio.sleep(0)
        await coordinator.shutdown()
        assert coordinator.closed

    asyncio.run(scenario())
