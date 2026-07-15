import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from app.rag.async_operation import run_blocking_operation_safely


T = TypeVar("T")


@dataclass(frozen=True)
class ToolOperationOutcome:
    value: Any = None
    timed_out: bool = False


class ToolOperationCoordinator:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._active_operation: asyncio.Task[Any] | None = None

    async def run(
        self,
        function: Callable[..., T],
        *args,
        timeout_seconds: float,
        **kwargs,
    ) -> ToolOperationOutcome:
        if timeout_seconds <= 0:
            return ToolOperationOutcome(timed_out=True)
        try:
            await asyncio.wait_for(self._lock.acquire(), timeout=timeout_seconds)
        except TimeoutError:
            return ToolOperationOutcome(timed_out=True)

        released = False

        def release_slot() -> None:
            nonlocal released
            if released:
                return
            released = True
            if self._lock.locked():
                self._lock.release()

        async def operation_wrapper() -> T:
            try:
                return await run_blocking_operation_safely(function, *args, **kwargs)
            finally:
                release_slot()

        operation_task = asyncio.create_task(operation_wrapper())
        self._active_operation = operation_task

        def _consume_result(task: asyncio.Task[Any]) -> None:
            try:
                task.result()
            except BaseException:
                pass
            finally:
                if self._active_operation is task:
                    self._active_operation = None

        operation_task.add_done_callback(_consume_result)

        try:
            value = await asyncio.wait_for(asyncio.shield(operation_task), timeout=timeout_seconds)
        except TimeoutError:
            return ToolOperationOutcome(timed_out=True)
        except asyncio.CancelledError:
            raise
        return ToolOperationOutcome(value=value, timed_out=False)

    def is_busy(self) -> bool:
        return self._active_operation is not None and not self._active_operation.done()

    async def shutdown(self, timeout_seconds: float = 1.0) -> None:
        active = self._active_operation
        if active is None:
            return
        try:
            await asyncio.wait_for(asyncio.shield(active), timeout=timeout_seconds)
        except TimeoutError:
            return
        except BaseException:
            return
