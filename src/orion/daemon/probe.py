"""Sondagem de hardware sem LLM e escolha de perfil de boot (ADR-035).

Determinístico, zero token: lê ``psutil`` e ``/proc/pressure``. Nada aqui importa gateway/providers.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal

import psutil
from pydantic import BaseModel

from orion.settings.models import PressureSettings

_PSI_RE = re.compile(r"^some\b.*?\bavg10=([0-9.]+)", re.MULTILINE)

BootProfile = Literal["minimal", "standard", "full"]

_MINIMAL = frozenset({"ipc", "scheduler", "notifier", "audit"})
_STANDARD = _MINIMAL | {"memory", "mcp", "telegram", "session"}
PROFILE_COMPONENTS: dict[BootProfile, frozenset[str]] = {
    "minimal": _MINIMAL,
    "standard": _STANDARD,
    "full": _STANDARD | {"embeddings"},
}


class HardwareSnapshot(BaseModel):
    """Foto instantânea da máquina."""

    mem_total_mb: float
    mem_available_mb: float
    cpu_count: int
    load1: float
    cpu_percent: float
    psi_cpu: float | None = None
    psi_mem: float | None = None
    psi_io: float | None = None
    on_battery: bool | None = None
    battery_percent: float | None = None
    disk_free_mb: float


def read_psi(path: Path) -> float | None:
    """Lê ``some avg10`` de um arquivo PSI; ``None`` se ausente ou ilegível."""
    try:
        text = path.read_text()
    except OSError:
        return None
    match = _PSI_RE.search(text)
    return float(match.group(1)) if match else None


class HardwareProbe:
    """Coleta :class:`HardwareSnapshot` a partir de ``psutil`` e ``/proc``."""

    def __init__(self, *, proc_root: Path = Path("/proc"), home: Path, ps: Any = psutil) -> None:
        self._proc = proc_root
        self._home = home
        self._ps = ps

    def snapshot(self) -> HardwareSnapshot:
        ps = self._ps
        vm = ps.virtual_memory()
        try:
            load1 = float(ps.getloadavg()[0])
        except (AttributeError, OSError):
            load1 = 0.0
        battery = None
        sensors = getattr(ps, "sensors_battery", None)
        if sensors is not None:
            try:
                battery = sensors()
            except (OSError, NotImplementedError):
                battery = None
        target = self._home if self._home.exists() else Path(self._home.anchor or "/")
        disk = ps.disk_usage(str(target))
        return HardwareSnapshot(
            mem_total_mb=vm.total / 1048576,
            mem_available_mb=vm.available / 1048576,
            cpu_count=int(ps.cpu_count() or 1),
            load1=load1,
            cpu_percent=min(1.0, max(0.0, float(ps.cpu_percent(interval=None)) / 100.0)),
            psi_cpu=read_psi(self._proc / "pressure" / "cpu"),
            psi_mem=read_psi(self._proc / "pressure" / "memory"),
            psi_io=read_psi(self._proc / "pressure" / "io"),
            on_battery=None if battery is None else not battery.power_plugged,
            battery_percent=None if battery is None else float(battery.percent),
            disk_free_mb=disk.free / 1048576,
        )


def choose_profile(
    snap: HardwareSnapshot, setting: Literal["auto", "minimal", "full"] = "auto"
) -> BootProfile:
    """Escolhe o perfil de boot; configuração explícita vence a heurística."""
    if setting == "minimal":
        return "minimal"
    if setting == "full":
        return "full"
    low_battery = bool(snap.on_battery) and (
        snap.battery_percent is not None and snap.battery_percent < 20
    )
    if snap.mem_total_mb < 4096 or snap.cpu_count <= 2 or low_battery or snap.disk_free_mb < 1024:
        return "minimal"
    if snap.mem_total_mb >= 16384 and snap.cpu_count >= 8 and not snap.on_battery:
        return "full"
    return "standard"


class StabilizeResult(BaseModel):
    """Resultado da espera por estabilização."""

    stable: bool
    waited_s: float
    samples: int


def _is_calm(snap: HardwareSnapshot, t: PressureSettings) -> bool:
    used = 1.0 - snap.mem_available_mb / snap.mem_total_mb if snap.mem_total_mb else 0.0
    if snap.cpu_percent >= t.exit_cpu or used >= t.exit_mem:
        return False
    return all(p is None or p < t.exit_psi for p in (snap.psi_cpu, snap.psi_mem, snap.psi_io))


async def wait_until_stable(
    probe: HardwareProbe,
    *,
    thresholds: PressureSettings,
    max_wait_s: float,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    interval_s: float = 5.0,
    required_stable: int = 3,
) -> StabilizeResult:
    """Espera N amostras calmas consecutivas; desiste em ``max_wait_s`` (stable=False)."""
    start = clock()
    samples = 0
    streak = 0
    while True:
        samples += 1
        streak = streak + 1 if _is_calm(probe.snapshot(), thresholds) else 0
        waited = clock() - start
        if streak >= required_stable:
            return StabilizeResult(stable=True, waited_s=waited, samples=samples)
        if waited >= max_wait_s:
            return StabilizeResult(stable=False, waited_s=waited, samples=samples)
        await sleep(min(interval_s, max(0.0, max_wait_s - waited)))
