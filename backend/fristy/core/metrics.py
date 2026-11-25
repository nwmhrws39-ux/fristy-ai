"""Background performance monitor (CPU, RAM, GPU, temperatures) with warnings."""
from __future__ import annotations

import asyncio
import collections
import time
from typing import Any

import psutil


class MetricsMonitor:
    def __init__(self, platform, bus, interval: float = 5.0):
        self.platform = platform
        self.bus = bus
        self.interval = interval
        self.history: collections.deque = collections.deque(maxlen=120)
        self._task = None
        self._gpu_every = 3
        self._n = 0
        self._last_gpu: list[dict] = []
        self._last_temps: dict[str, float] = {}

    def sample(self) -> dict[str, Any]:
        vm = psutil.virtual_memory()
        self._n += 1
        if self._n % self._gpu_every == 1:
            try:
                self._last_gpu = self.platform.gpu_info()
            except Exception:
                self._last_gpu = []
            try:
                self._last_temps = self.platform.temperatures()
            except Exception:
                self._last_temps = {}
        gpu = self._last_gpu[0] if self._last_gpu else {}
        try:
            proc = psutil.Process()
            own = {"rss_mb": round(proc.memory_info().rss / 1e6, 1), "cpu_percent": proc.cpu_percent(None)}
        except psutil.Error:
            own = {}
        return {
            "ts": time.time(),
            "cpu_percent": psutil.cpu_percent(None),
            "ram_percent": vm.percent,
            "ram_used_gb": round(vm.used / 1e9, 2),
            "ram_total_gb": round(vm.total / 1e9, 2),
            "gpu_name": gpu.get("name"),
            "gpu_percent": gpu.get("utilization_percent"),
            "gpu_temp_c": gpu.get("temperature_c"),
            "temperatures": self._last_temps,
            "backend": own,
        }

    def latest(self) -> dict[str, Any]:
        if not self.history:
            self.history.append(self.sample())
        return self.history[-1]

    def warnings(self) -> list[str]:
        w = []
        recent = list(self.history)[-6:]
        if len(recent) >= 3 and all(s["cpu_percent"] > 90 for s in recent[-3:]):
            w.append("CPU usage has been above 90% for the last 15 seconds.")
        if recent and recent[-1]["ram_percent"] > 90:
            w.append(f"RAM usage is high ({recent[-1]['ram_percent']:.0f}%).")
        if recent:
            for k, v in (recent[-1].get("temperatures") or {}).items():
                if v and v >= 85:
                    w.append(f"High temperature on {k}: {v:.0f}°C.")
            g = recent[-1].get("gpu_temp_c")
            if g and g >= 85 and not any("gpu" in x for x in w):
                w.append(f"High GPU temperature: {g:.0f}°C.")
        return w

    def start(self) -> None:
        if self._task is None:
            psutil.cpu_percent(None)
            self._task = asyncio.create_task(self._loop())

    async def _loop(self) -> None:
        while True:
            try:
                s = await asyncio.to_thread(self.sample)
                self.history.append(s)
                self.bus.publish("metrics", metrics=s, warnings=self.warnings())
            except Exception:
                pass
            await asyncio.sleep(self.interval)
