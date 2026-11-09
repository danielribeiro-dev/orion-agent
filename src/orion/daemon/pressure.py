"""Monitor de pressão determinístico com histerese (ADR-035).

Mede a pressão DESCONTANDO o consumo do próprio ORION, para que a carga causada por ele não o
faça dormir. Sob pressão externa, põe componentes não essenciais para dormir; ao normalizar,
acorda. Zero token: sem LLM.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Literal

import psutil
from pydantic import BaseModel

from orion.daemon.probe import read_psi
from orion.daemon.sleepable import ComponentRegistry
from orion.settings.models import PressureSettings

PressureState = Literal["normal", "pressured"]
Transition = Literal["enter", "exit"]


class PressureSample(BaseModel):
    """Uma amostra de pressão. Todas as frações em 0..1, exceto ``psi`` (percentual)."""

    cpu: float
    mem: float
    psi: float | None = None
    self_cpu: float = 0.0
    self_mem: float = 0.0

    @property
    def effective_cpu(self) -> float:
        return max(0.0, self.cpu - self.self_cpu)

    @property
    def effective_mem(self) -> float:
        return max(0.0, self.mem - self.self_mem)


class PressureMonitor:
    """Decide entrada/saída de pressão e aplica sono/despertar ao registro."""

    def __init__(
        self,
        registry: ComponentRegistry,
        settings: PressureSettings,
        sampler: Callable[[], PressureSample],
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._registry = registry
        self._settings = settings
        self._sampler = sampler
        self._clock = clock
        self.state: PressureState = "normal"
        self.transitions: list[tuple[float, str]] = []
        self._since = clock()
        self._stop = asyncio.Event()

    def evaluate(self, sample: PressureSample) -> Transition | None:
        """Decisão pura (sem efeitos): respeita histerese e tempo mínimo no estado."""
        s = self._settings
        if self._clock() - self._since < s.min_dwell_s:
            return None
        psi = sample.psi
        if self.state == "normal":
            if (
                sample.effective_cpu >= s.enter_cpu
                or sample.effective_mem >= s.enter_mem
                or (psi is not None and psi >= s.enter_psi)
            ):
                return "enter"
            return None
        if (
            sample.effective_cpu < s.exit_cpu
            and sample.effective_mem < s.exit_mem
            and (psi is None or psi < s.exit_psi)
        ):
            return "exit"
        return None

    async def tick(self) -> Transition | None:
        decision = self.evaluate(self._sampler())
        if decision is None:
            return None
        if decision == "enter":
            await self._registry.sleep_nonessential()
            self.state = "pressured"
        else:
            await self._registry.wake_all()
            self.state = "normal"
        now = self._clock()
        self._since = now
        self.transitions.append((now, decision))
        return decision

    def stop(self) -> None:
        self._stop.set()

    async def run(self, sleep: Callable[[float], Awaitable[object]] = asyncio.sleep) -> None:
        """Laço de amostragem a cada ``sample_s`` até ``stop()``."""
        while not self._stop.is_set():
            await self.tick()
            await sleep(self._settings.sample_s)


def default_sampler(
    process: psutil.Process | None = None,
    *,
    psi_path: Path = Path("/proc/pressure/memory"),
) -> Callable[[], PressureSample]:
    """Amostrador real via psutil, separando o consumo do próprio processo."""
    proc = process or psutil.Process()
    ncpu = psutil.cpu_count() or 1
    psutil.cpu_percent(interval=None)
    proc.cpu_percent(None)

    def sample() -> PressureSample:
        vm = psutil.virtual_memory()
        total = vm.total or 1
        return PressureSample(
            cpu=min(1.0, psutil.cpu_percent(interval=None) / 100.0),
            mem=min(1.0, max(0.0, 1.0 - vm.available / total)),
            psi=read_psi(psi_path),
            self_cpu=min(1.0, proc.cpu_percent(None) / 100.0 / ncpu),
            self_mem=min(1.0, proc.memory_info().rss / total),
        )

    return sample
