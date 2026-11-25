"""Human-in-the-loop confirmation broker.

Fails closed: if no UI is connected, or the user doesn't answer before the
timeout, the action is denied.
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PendingConfirmation:
    id: str
    action: str
    summary: str
    risk: str
    source: str
    details: dict[str, Any]
    future: asyncio.Future = field(repr=False)


class ConfirmationBroker:
    def __init__(self, bus, timeout: float = 120.0):
        self.bus = bus
        self.timeout = timeout
        self._pending: dict[str, PendingConfirmation] = {}
        self.ui_connected = lambda: True

    async def request(
        self,
        action: str,
        summary: str,
        risk: str,
        source: str,
        details: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> bool:
        if not self.ui_connected():
            return False
        loop = asyncio.get_running_loop()
        cid = uuid.uuid4().hex
        pending = PendingConfirmation(
            id=cid,
            action=action,
            summary=summary,
            risk=risk,
            source=source,
            details=details or {},
            future=loop.create_future(),
        )
        self._pending[cid] = pending
        self.bus.publish(
            "confirmation.request",
            id=cid,
            action=action,
            summary=summary,
            risk=risk,
            source=source,
            details=pending.details,
            timeout=timeout or self.timeout,
        )
        try:
            return bool(await asyncio.wait_for(asyncio.shield(pending.future), timeout or self.timeout))
        except asyncio.TimeoutError:
            return False
        finally:
            self._pending.pop(cid, None)
            self.bus.publish("confirmation.closed", id=cid)

    def resolve(self, cid: str, approved: bool) -> bool:
        p = self._pending.get(cid)
        if not p or p.future.done():
            return False
        p.future.set_result(bool(approved))
        return True

    def deny_all(self) -> None:
        for p in list(self._pending.values()):
            if not p.future.done():
                p.future.set_result(False)

    def pending(self) -> list[dict[str, Any]]:
        return [
            {"id": p.id, "action": p.action, "summary": p.summary, "risk": p.risk, "source": p.source, "details": p.details}
            for p in self._pending.values()
        ]
