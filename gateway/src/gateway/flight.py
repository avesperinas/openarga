from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Hashable
from typing import TypeVar

T = TypeVar("T")


class Flight:
    def __init__(self) -> None:
        self._running: dict[Hashable, asyncio.Future] = {}

    async def run(self, key: Hashable, ask: Callable[[], Awaitable[T]]) -> T:
        running = self._running.get(key)
        if running is None:
            running = asyncio.ensure_future(ask())
            self._running[key] = running
            running.add_done_callback(lambda done: self._land(key, done))
        return await asyncio.shield(running)

    def _land(self, key: Hashable, done: asyncio.Future) -> None:
        if self._running.get(key) is done:
            del self._running[key]
