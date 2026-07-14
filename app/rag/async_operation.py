import asyncio
from collections.abc import Callable
from typing import TypeVar


T = TypeVar("T")


async def run_blocking_operation_safely(
    function: Callable[..., T],
    *args,
    cleanup_timeout_seconds: float = 10.0,
    **kwargs,
) -> T:
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError as exc:
        while True:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=cleanup_timeout_seconds)
                break
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        raise exc
