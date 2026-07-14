import asyncio
import threading
import time

from app.rag.operation_coordinator import VectorOperationCoordinator


def test_coordinator_returns_cancelled_request_quickly_and_keeps_operation_running() -> None:
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def slow_operation() -> str:
        started.set()
        release.wait(timeout=1)
        finished.set()
        return "ok"

    async def scenario() -> None:
        coordinator = VectorOperationCoordinator()
        task = asyncio.create_task(coordinator.run(slow_operation, acquire_timeout_seconds=0.05))
        while not started.is_set():
            await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        busy = False
        try:
            await coordinator.run(lambda: "later", acquire_timeout_seconds=0.05)
        except TimeoutError:
            busy = True
        assert busy is True
        release.set()
        while not finished.is_set():
            await asyncio.sleep(0.01)
        assert await coordinator.run(lambda: "done", acquire_timeout_seconds=0.05) == "done"

    asyncio.run(scenario())


def test_coordinator_releases_lock_on_error() -> None:
    async def scenario() -> None:
        coordinator = VectorOperationCoordinator()

        def failing() -> None:
            raise RuntimeError("boom")

        try:
            await coordinator.run(failing, acquire_timeout_seconds=0.05)
        except RuntimeError:
            pass
        assert await coordinator.run(lambda: "ok", acquire_timeout_seconds=0.05) == "ok"

    asyncio.run(scenario())


def test_coordinator_shutdown_does_not_break_active_operation() -> None:
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def slow_operation() -> str:
        started.set()
        release.wait(timeout=1)
        finished.set()
        return "ok"

    async def scenario() -> None:
        coordinator = VectorOperationCoordinator()
        task = asyncio.create_task(coordinator.run(slow_operation, acquire_timeout_seconds=0.05))
        while not started.is_set():
            await asyncio.sleep(0.01)
        await coordinator.shutdown(timeout_seconds=0.01)
        assert not finished.is_set()
        release.set()
        assert await task == "ok"

    asyncio.run(scenario())
