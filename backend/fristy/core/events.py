"""In-process async event bus used to push live state to the desktop UI."""
from __future__ import annotations

import asyncio
import time
from typing import Any


class EventBus:
    def __init__(self, max_queue: int = 1000):
        self._subscribers: set[asyncio.Queue] = set()
        self._max_queue = max_queue
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def publish(self, type_: str, **data: Any) -> None:
        event = {"type": type_, "ts": time.time(), **data}
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Slow consumer: drop the oldest event rather than block the backend.
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:
                    pass

    def publish_threadsafe(self, type_: str, **data: Any) -> None:
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(lambda: self.publish(type_, **data))
        else:
            self.publish(type_, **data)
