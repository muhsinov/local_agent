import asyncio
from collections.abc import Callable
from typing import Any, TypeVar

from app.rag.async_operation import run_blocking_operation_safely


T = TypeVar("T")


class VectorOperationCoordinator:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._active_operation: asyncio.Task[Any] | None = None

    async def run(
        self,
        function: Callable[..., T],
        *args,
        acquire_timeout_seconds: float,
        **kwargs,
    ) -> T:
        try:
            await asyncio.wait_for(self._lock.acquire(), timeout=acquire_timeout_seconds)
        except TimeoutError as exc:
            raise TimeoutError from exc

        async def operation_wrapper() -> T:
            try:
                return await run_blocking_operation_safely(function, *args, **kwargs)
            finally:
                if self._lock.locked():
                    self._lock.release()

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
            return await asyncio.shield(operation_task)
        except asyncio.CancelledError:
            raise

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
