import asyncio
from datetime import datetime, timezone


class RuntimeLifecycle:
    def __init__(self) -> None:
        self.accepting_requests = True
        self.draining = False
        self.started_at = datetime.now(timezone.utc)
        self.startup_ready = False
        self._active = 0
        self._condition = asyncio.Condition()

    async def enter(self) -> bool:
        async with self._condition:
            if self.draining or not self.accepting_requests:
                return False
            self._active += 1
            return True

    async def exit(self) -> None:
        async with self._condition:
            self._active = max(0, self._active - 1)
            self._condition.notify_all()

    async def begin_drain(self) -> None:
        async with self._condition:
            self.accepting_requests = False
            self.draining = True

    async def wait_for_active(self, timeout: float) -> bool:
        async def wait():
            async with self._condition:
                await self._condition.wait_for(lambda: self._active == 0)
        try:
            await asyncio.wait_for(wait(), timeout=timeout)
            return True
        except TimeoutError:
            return False
