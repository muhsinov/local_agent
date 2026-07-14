import asyncio
import threading
import time

from app.rag.async_operation import run_blocking_operation_safely


def test_run_blocking_operation_waits_for_completion_after_cancellation() -> None:
    started = threading.Event()
    finished = threading.Event()

    def slow_operation() -> str:
        started.set()
        time.sleep(0.2)
        finished.set()
        return "ok"

    async def scenario() -> None:
        task = asyncio.create_task(run_blocking_operation_safely(slow_operation, cleanup_timeout_seconds=0.05))
        while not started.is_set():
            await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert finished.is_set()

    asyncio.run(scenario())
