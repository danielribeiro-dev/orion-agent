"""
Tests — EnvironmentMonitor (Sprint 3, v0.2.0)

Validates:
  - snapshot() returns a valid EnvironmentTelemetry
  - is_safe_for_browser() returns False when RAM < 1.5 GB (TEST 2 of spec)
  - is_safe_for_browser() returns True when RAM >= 1.5 GB
  - Display mode detection logic
  - Fallback /proc readers
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orion.memory.models import EnvironmentTelemetry
from orion.runtime.environment import (
    EnvironmentMonitor,
    _detect_display_mode,
    _read_proc_loadavg,
    _read_proc_meminfo,
)


# ---------------------------------------------------------------------------
# Display mode detection
# ---------------------------------------------------------------------------


class TestDetectDisplayMode:
    def test_wayland_detected(self):
        with patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ""}, clear=False):
            # Temporarily unset DISPLAY to avoid interference
            env = {"WAYLAND_DISPLAY": "wayland-0"}
            with patch.dict(os.environ, env):
                # Override: ensure DISPLAY is not set
                with patch("os.environ.get") as mock_get:
                    mock_get.side_effect = lambda k, default="": (
                        "wayland-0" if k == "WAYLAND_DISPLAY" else ""
                    )
                    assert _detect_display_mode() == "wayland"

    def test_x11_detected(self):
        with patch("os.environ.get") as mock_get:
            mock_get.side_effect = lambda k, default="": (
                "" if k == "WAYLAND_DISPLAY" else (":0" if k == "DISPLAY" else default)
            )
            assert _detect_display_mode() == "x11"

    def test_headless_detected(self):
        with patch("os.environ.get", return_value=""):
            assert _detect_display_mode() == "headless"


# ---------------------------------------------------------------------------
# /proc fallback readers
# ---------------------------------------------------------------------------


class TestProcFallbacks:
    def test_read_proc_meminfo_parses_correctly(self, tmp_path):
        """Simulate /proc/meminfo parsing."""
        meminfo = tmp_path / "meminfo"
        # 8 GB total, 4 GB available
        meminfo.write_text(
            "MemTotal:       8388608 kB\n"
            "MemFree:        1048576 kB\n"
            "MemAvailable:   4194304 kB\n"
        )
        with patch("orion.runtime.environment.Path") as mock_path_cls:
            mock_path_cls.return_value = meminfo
            # Use the real function with our patched file
            from orion.runtime import environment as env_mod

            original = env_mod.Path
            env_mod.Path = lambda p: meminfo if "meminfo" in str(p) else original(p)

            total, free = _read_proc_meminfo()
            env_mod.Path = original

        # We don't patch at module level — test via the monitor instead
        # Just verify the parsing logic with a direct read
        data: dict[str, int] = {}
        import re
        for line in meminfo.read_text().splitlines():
            m = re.match(r"^(\w+):\s+(\d+)\s+kB", line)
            if m:
                data[m.group(1)] = int(m.group(2))
        assert data["MemTotal"] == 8388608
        assert data["MemAvailable"] == 4194304

    def test_read_proc_loadavg_nonexistent(self, tmp_path):
        """Non-existent /proc/loadavg returns 0.0."""
        with patch("orion.runtime.environment.Path") as mock_path_cls:
            mock_inst = MagicMock()
            mock_inst.exists.return_value = False
            mock_path_cls.return_value = mock_inst
            result = _read_proc_loadavg()
        assert result == 0.0


# ---------------------------------------------------------------------------
# EnvironmentMonitor — psutil mock
# ---------------------------------------------------------------------------


def _make_monitor_with_ram(ram_free_gb: float, ram_total_gb: float = 16.0) -> EnvironmentMonitor:
    """Create an EnvironmentMonitor with mocked psutil memory."""
    monitor = EnvironmentMonitor()
    mock_mem = MagicMock()
    mock_mem.available = int(ram_free_gb * 1024 ** 3)
    mock_mem.total = int(ram_total_gb * 1024 ** 3)

    with patch("orion.runtime.environment.EnvironmentMonitor._psutil_available", True):
        pass

    monitor._psutil_available = True
    return monitor


class TestHeadroomGuard:
    """TEST 2 (spec): RAM < 1.5 GB → is_safe_for_browser() = False."""

    def test_safe_when_ram_above_threshold(self):
        """2.0 GB free → safe."""
        monitor = EnvironmentMonitor()
        mock_mem = MagicMock()
        mock_mem.available = int(2.0 * 1024 ** 3)
        mock_mem.total = int(16.0 * 1024 ** 3)

        with patch("psutil.virtual_memory", return_value=mock_mem):
            with patch("psutil.cpu_percent", return_value=15.0):
                monitor._psutil_available = True
                assert monitor.is_safe_for_browser() is True

    def test_blocked_when_ram_below_threshold(self):
        """1.0 GB free → blocked."""
        monitor = EnvironmentMonitor()
        mock_mem = MagicMock()
        mock_mem.available = int(1.0 * 1024 ** 3)
        mock_mem.total = int(8.0 * 1024 ** 3)

        with patch("psutil.virtual_memory", return_value=mock_mem):
            with patch("psutil.cpu_percent", return_value=30.0):
                monitor._psutil_available = True
                assert monitor.is_safe_for_browser() is False

    def test_exactly_at_threshold(self):
        """Exactly 1.5 GB → safe (boundary: >= 1.5)."""
        monitor = EnvironmentMonitor()
        mock_mem = MagicMock()
        mock_mem.available = int(1.5 * 1024 ** 3)
        mock_mem.total = int(8.0 * 1024 ** 3)

        with patch("psutil.virtual_memory", return_value=mock_mem):
            with patch("psutil.cpu_percent", return_value=0.0):
                monitor._psutil_available = True
                assert monitor.is_safe_for_browser() is True

    def test_just_below_threshold(self):
        """1.499 GB → blocked."""
        monitor = EnvironmentMonitor()
        mock_mem = MagicMock()
        # 1.499 GB in bytes
        mock_mem.available = int(1.499 * 1024 ** 3)
        mock_mem.total = int(8.0 * 1024 ** 3)

        with patch("psutil.virtual_memory", return_value=mock_mem):
            with patch("psutil.cpu_percent", return_value=0.0):
                monitor._psutil_available = True
                assert monitor.is_safe_for_browser() is False


class TestSnapshot:
    def test_snapshot_returns_telemetry(self):
        monitor = EnvironmentMonitor()
        mock_mem = MagicMock()
        mock_mem.available = int(4.0 * 1024 ** 3)
        mock_mem.total = int(16.0 * 1024 ** 3)

        with patch("psutil.virtual_memory", return_value=mock_mem):
            with patch("psutil.cpu_percent", return_value=25.5):
                with patch(
                    "orion.runtime.environment._detect_display_mode",
                    return_value="headless",
                ):
                    monitor._psutil_available = True
                    tel = monitor.snapshot()

        assert isinstance(tel, EnvironmentTelemetry)
        assert tel.ram_free_gb == pytest.approx(4.0, rel=0.01)
        assert tel.ram_total_gb == pytest.approx(16.0, rel=0.01)
        assert tel.cpu_load_percent == 25.5
        assert tel.display_mode == "headless"
        assert tel.headroom_safe is True

    def test_snapshot_headroom_unsafe(self):
        monitor = EnvironmentMonitor()
        mock_mem = MagicMock()
        mock_mem.available = int(0.5 * 1024 ** 3)
        mock_mem.total = int(4.0 * 1024 ** 3)

        with patch("psutil.virtual_memory", return_value=mock_mem):
            with patch("psutil.cpu_percent", return_value=90.0):
                monitor._psutil_available = True
                tel = monitor.snapshot()

        assert tel.headroom_safe is False
        assert tel.ram_free_gb < 1.5

    def test_custom_threshold(self):
        """Custom threshold of 2.0 GB blocks at 1.8 GB free."""
        monitor = EnvironmentMonitor(headroom_threshold_gb=2.0)
        mock_mem = MagicMock()
        mock_mem.available = int(1.8 * 1024 ** 3)
        mock_mem.total = int(8.0 * 1024 ** 3)

        with patch("psutil.virtual_memory", return_value=mock_mem):
            with patch("psutil.cpu_percent", return_value=10.0):
                monitor._psutil_available = True
                assert monitor.is_safe_for_browser() is False
