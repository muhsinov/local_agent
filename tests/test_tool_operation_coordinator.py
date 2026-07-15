import asyncio
import threading

from app.agent.tool_operation_coordinator import ToolOperationCoordinator


def test_sync_tool_timeout_leaves_underlying_thread_running() -> None:
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def slow_operation() -> str:
        started.set()
        release.wait(timeout=1)
        finished.set()
        return "ok"

    async def scenario() -> None:
        coordinator = ToolOperationCoordinator()
        outcome = await coordinator.run(slow_operation, timeout_seconds=0.01)
        assert outcome.timed_out is True
        assert started.is_set() is True
        assert finished.is_set() is False
        release.set()
        await coordinator.shutdown(timeout_seconds=0.2)
        assert finished.is_set() is True

    asyncio.run(scenario())


def test_second_tool_does_not_start_until_first_thread_finishes() -> None:
    first_started = threading.Event()
    second_started = threading.Event()
    release_first = threading.Event()

    def first_operation() -> str:
        first_started.set()
        release_first.wait(timeout=1)
        return "first"

    def second_operation() -> str:
        second_started.set()
        return "second"

    async def scenario() -> None:
        coordinator = ToolOperationCoordinator()
        first = asyncio.create_task(coordinator.run(first_operation, timeout_seconds=0.01))
        while not first_started.is_set():
            await asyncio.sleep(0.001)
        second = await coordinator.run(second_operation, timeout_seconds=0.01)
        assert second.timed_out is True
        assert second_started.is_set() is False
        release_first.set()
        await coordinator.shutdown(timeout_seconds=0.2)
        assert (await first).timed_out is True
        third = await coordinator.run(second_operation, timeout_seconds=0.05)
        assert third.value == "second"
        assert second_started.is_set() is True

    asyncio.run(scenario())


def test_background_exception_is_consumed() -> None:
    release = threading.Event()
    captured: list[dict] = []

    def exception_handler(loop, context) -> None:
        captured.append(context)

    def failing_operation() -> None:
        release.wait(timeout=1)
        raise RuntimeError("boom")

    async def scenario() -> None:
        coordinator = ToolOperationCoordinator()
        loop = asyncio.get_running_loop()
        previous = loop.get_exception_handler()
        loop.set_exception_handler(exception_handler)
        try:
            outcome = await coordinator.run(failing_operation, timeout_seconds=0.01)
            assert outcome.timed_out is True
            release.set()
            await coordinator.shutdown(timeout_seconds=0.2)
        finally:
            loop.set_exception_handler(previous)
        assert captured == []

    asyncio.run(scenario())


def test_shutdown_does_not_corrupt_active_operation() -> None:
    started = threading.Event()
    release = threading.Event()

    def slow_operation() -> str:
        started.set()
        release.wait(timeout=1)
        return "ok"

    async def scenario() -> None:
        coordinator = ToolOperationCoordinator()
        task = asyncio.create_task(coordinator.run(slow_operation, timeout_seconds=0.2))
        while not started.is_set():
            await asyncio.sleep(0.001)
        await coordinator.shutdown(timeout_seconds=0.01)
        assert coordinator.is_busy() is True
        release.set()
        outcome = await task
        assert outcome.value == "ok"

    asyncio.run(scenario())
