"""
O.R.I.O.N — Environment Monitor (Sprint 3, v0.2.0)

Sphere 3 — system_environment:
  Passive hardware telemetry via psutil with deterministic Headroom Guard.
  Blocks resource-heavy processes (e.g. browsers) when free RAM < 1.5 GB.

Fallbacks:
  - /proc/meminfo  → if psutil is unavailable (unlikely in CI)
  - /proc/loadavg  → CPU load fallback

ADR-015: Environment Guard
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from orion.memory.models import EnvironmentTelemetry

logger = logging.getLogger(__name__)

_HEADROOM_THRESHOLD_GB = 1.5


def _detect_display_mode() -> str:
    """Detect the active display server: 'wayland', 'x11', or 'headless'."""
    wayland = os.environ.get("WAYLAND_DISPLAY", "")
    x11 = os.environ.get("DISPLAY", "")
    if wayland:
        return "wayland"
    if x11:
        return "x11"
    return "headless"


def _read_proc_meminfo() -> tuple[float, float]:
    """
    Fallback memory reader via /proc/meminfo.

    Returns:
        (ram_total_gb, ram_free_gb) — using MemAvailable for free if present.
    """
    meminfo = Path("/proc/meminfo")
    if not meminfo.exists():
        return (0.0, 0.0)

    data: dict[str, int] = {}
    for line in meminfo.read_text().splitlines():
        match = re.match(r"^(\w+):\s+(\d+)\s+kB", line)
        if match:
            data[match.group(1)] = int(match.group(2))

    total_kb = data.get("MemTotal", 0)
    # Prefer MemAvailable (real usable) over MemFree (excludes buffers/cache)
    free_kb = data.get("MemAvailable", data.get("MemFree", 0))
    return (total_kb / (1024 * 1024), free_kb / (1024 * 1024))


def _read_proc_loadavg() -> float:
    """Fallback CPU load (1-minute average) via /proc/loadavg."""
    loadavg = Path("/proc/loadavg")
    if not loadavg.exists():
        return 0.0
    try:
        return float(loadavg.read_text().split()[0])
    except (ValueError, IndexError):
        return 0.0


class EnvironmentMonitor:
    """
    Passive hardware telemetry monitor with deterministic Headroom Guard.

    Usage::

        monitor = EnvironmentMonitor()
        telemetry = monitor.snapshot()
        if not monitor.is_safe_for_browser():
            print("⚠️  RAM insuficiente para abrir navegadores.")
    """

    def __init__(self, headroom_threshold_gb: float = _HEADROOM_THRESHOLD_GB) -> None:
        self._threshold_gb = headroom_threshold_gb
        self._psutil_available = self._check_psutil()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def snapshot(self) -> EnvironmentTelemetry:
        """Collect and return a point-in-time hardware telemetry snapshot."""
        ram_total_gb, ram_free_gb, cpu_load = self._collect_metrics()
        display_mode = _detect_display_mode()
        gpu_name = self._detect_gpu()
        headroom_safe = ram_free_gb >= self._threshold_gb

        return EnvironmentTelemetry(
            ram_free_gb=round(ram_free_gb, 2),
            ram_total_gb=round(ram_total_gb, 2),
            cpu_load_percent=round(cpu_load, 1),
            display_mode=display_mode,
            gpu_name=gpu_name,
            headroom_safe=headroom_safe,
        )

    def is_safe_for_browser(self) -> bool:
        """
        Deterministic Headroom Guard.

        Returns:
            True  — free RAM >= 1.5 GB; it is safe to launch a browser.
            False — free RAM < 1.5 GB; a browser launch should be blocked.
        """
        _, ram_free_gb, _ = self._collect_metrics()
        safe = ram_free_gb >= self._threshold_gb
        if not safe:
            logger.warning(
                "HeadroomGuard: RAM livre (%.2f GB) abaixo do limiar (%.1f GB). "
                "Abertura de navegadores bloqueada preventivamente.",
                ram_free_gb,
                self._threshold_gb,
            )
        return safe

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_psutil() -> bool:
        try:
            import psutil  # noqa: F401

            return True
        except ImportError:
            logger.warning("psutil not available — using /proc fallback.")
            return False

    def _collect_metrics(self) -> tuple[float, float, float]:
        """
        Collect (ram_total_gb, ram_free_gb, cpu_load_percent).

        Prefers psutil; falls back to /proc filesystem reads.
        """
        if self._psutil_available:
            try:
                import psutil

                mem = psutil.virtual_memory()
                ram_total_gb = mem.total / (1024 ** 3)
                ram_free_gb = mem.available / (1024 ** 3)
                # interval=None → cached value (non-blocking, safe for repeated calls)
                cpu_load = psutil.cpu_percent(interval=None)
                return (ram_total_gb, ram_free_gb, cpu_load)
            except Exception as exc:  # pragma: no cover
                logger.warning("psutil error (%s); falling back to /proc.", exc)

        # /proc fallback
        ram_total_gb, ram_free_gb = _read_proc_meminfo()
        cpu_load = _read_proc_loadavg()
        return (ram_total_gb, ram_free_gb, cpu_load)

    @staticmethod
    def _detect_gpu() -> str | None:
        """
        Best-effort GPU name detection via psutil or /sys filesystem.
        Returns None if no GPU is detectable in this environment.
        """
        # Try reading from /sys/class/drm (DRM GPU driver names)
        drm_path = Path("/sys/class/drm")
        if drm_path.exists():
            for entry in sorted(drm_path.iterdir()):
                vendor_file = entry / "device" / "vendor"
                if vendor_file.exists():
                    return entry.name  # e.g. "card0"
        return None
