import asyncio
from collections.abc import Callable
from typing import TypeVar


T = TypeVar("T")


async def run_blocking_operation_safely(
    function: Callable[..., T],
    *args,
    **kwargs,
) -> T:
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    return await asyncio.shield(task)
