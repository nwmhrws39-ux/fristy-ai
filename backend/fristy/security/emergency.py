"""Emergency stop: cancels every running agent run, automation and input action."""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Callable


class StopController:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._callbacks: list[Callable[[], None]] = []
        self._lock = threading.Lock()
        self.last_stop_at: float | None = None
        self._stop_event = threading.Event()

    def register(self, run_id: str, task: asyncio.Task) -> None:
        with self._lock:
            self._tasks[run_id] = task
        task.add_done_callback(lambda _t: self.unregister(run_id))

    def unregister(self, run_id: str) -> None:
        with self._lock:
            self._tasks.pop(run_id, None)

    def on_stop(self, fn: Callable[[], None]) -> None:
        self._callbacks.append(fn)

    @property
    def active_runs(self) -> list[str]:
        with self._lock:
            return list(self._tasks)

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            t = self._tasks.get(run_id)
        if t and not t.done():
            t.cancel()
            return True
        return False

    def stopped_recently(self, window: float = 1.5) -> bool:
        """Input helpers check this so a stop interrupts long typing/click loops."""
        return self._stop_event.is_set() and self.last_stop_at is not None and (
            time.time() - self.last_stop_at < window
        )

    def emergency_stop(self) -> int:
        self.last_stop_at = time.time()
        self._stop_event.set()
        with self._lock:
            tasks = list(self._tasks.values())
        n = 0
        for t in tasks:
            if not t.done():
                t.cancel()
                n += 1
        for fn in self._callbacks:
            try:
                fn()
            except Exception:
                pass
        return n

    def clear(self) -> None:
        self._stop_event.clear()
