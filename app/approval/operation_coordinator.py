import asyncio
from collections.abc import Awaitable, Callable
from typing import Any


class ApprovalOperationCoordinator:
    """Owns approval lifecycle tasks independently from HTTP request tasks."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._active: dict[str, asyncio.Task[Any]] = {}
        self.accepting_operations = True
        self.draining = False
        self.closed = False

    def begin_drain(self) -> None:
        if self.closed:
            return
        self.accepting_operations = False
        self.draining = True

    def start(self) -> None:
        self.accepting_operations = True
        self.draining = False
        self.closed = False

    @property
    def state(self) -> str:
        return "closed" if self.closed else "draining" if self.draining else "accepting"

    async def start_or_join(
        self,
        *,
        approval_id: str,
        operation_factory: Callable[[], Awaitable[Any]],
    ) -> asyncio.Task[Any]:
        async with self._lock:
            if not self.accepting_operations:
                raise RuntimeError("APPROVAL_COORDINATOR_DRAINING")
            existing = self._active.get(approval_id)
            if existing is not None and not existing.done():
                return existing
            task = asyncio.create_task(operation_factory(), name=f"approval:{approval_id}")
            self._active[approval_id] = task
            task.add_done_callback(self._consume)
            return task

    def _consume(self, task: asyncio.Task[Any]) -> None:
        try:
            task.result()
        except BaseException:
            pass
        for approval_id, active in list(self._active.items()):
            if active is task:
                self._active.pop(approval_id, None)

    def active_ids(self) -> set[str]:
        return {approval_id for approval_id, task in self._active.items() if not task.done()}

    def is_active(self, approval_id: str) -> bool:
        task = self._active.get(approval_id)
        return task is not None and not task.done()

    async def shutdown(self, timeout_seconds: float = 1.0) -> None:
        tasks = [task for task in self._active.values() if not task.done()]
        if not tasks:
            self.closed = True
            return
        try:
            await asyncio.wait_for(
                asyncio.gather(*(asyncio.shield(task) for task in tasks), return_exceptions=True),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            pass
        self.closed = True
