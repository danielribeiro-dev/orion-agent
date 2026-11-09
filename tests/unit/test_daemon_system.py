"""Testes de probe, sleepable, pressure e service do daemon (ADR-032/035)."""

from __future__ import annotations

import ast
import asyncio
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from orion.daemon.pressure import PressureMonitor, PressureSample, default_sampler
from orion.daemon.probe import (
    PROFILE_COMPONENTS,
    HardwareProbe,
    HardwareSnapshot,
    choose_profile,
    read_psi,
    wait_until_stable,
)
from orion.daemon.service import (
    UNIT_NAME,
    CommandResult,
    ServiceError,
    ServiceManager,
    SubprocessRunner,
    render_unit,
)
from orion.daemon.sleepable import (
    ComponentNotAllowed,
    ComponentRegistry,
    FunctionComponent,
    Sleepable,
)
from orion.settings.models import PressureSettings

MB = 1048576


def snap(**kw: Any) -> HardwareSnapshot:
    base: dict[str, Any] = {
        "mem_total_mb": 8192,
        "mem_available_mb": 6000,
        "cpu_count": 4,
        "load1": 0.2,
        "cpu_percent": 0.1,
        "disk_free_mb": 50000,
    }
    base.update(kw)
    return HardwareSnapshot(**base)


class FakePs:
    def __init__(self, cpu: float = 10.0, battery: Any = None, avail_mb: int = 6000) -> None:
        self.cpu = cpu
        self.battery = battery
        self.avail = avail_mb

    def virtual_memory(self) -> Any:
        return SimpleNamespace(total=8192 * MB, available=self.avail * MB)

    def getloadavg(self) -> tuple[float, float, float]:
        return (0.5, 0.4, 0.3)

    def cpu_count(self) -> int:
        return 4

    def cpu_percent(self, interval: float | None = None) -> float:
        return self.cpu

    def sensors_battery(self) -> Any:
        return self.battery

    def disk_usage(self, path: str) -> Any:
        return SimpleNamespace(free=20000 * MB)


# ---------------------------------------------------------------- probe
def test_probe_snapshot_with_psi(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    (proc / "pressure").mkdir(parents=True)
    (proc / "pressure" / "cpu").write_text("some avg10=1.23 avg60=0.5 avg300=0.1 total=99\n")
    (proc / "pressure" / "memory").write_text(
        "some avg10=7.50 avg60=0 avg300=0 total=1\nfull avg10=2.0 avg60=0 avg300=0 total=1\n"
    )
    bat = SimpleNamespace(power_plugged=False, percent=55)
    s = HardwareProbe(proc_root=proc, home=tmp_path, ps=FakePs(battery=bat)).snapshot()
    assert s.psi_cpu == 1.23 and s.psi_mem == 7.5 and s.psi_io is None
    assert s.on_battery is True and s.battery_percent == 55
    assert s.cpu_percent == pytest.approx(0.1) and s.load1 == 0.5 and s.cpu_count == 4
    assert s.disk_free_mb == 20000


def test_probe_missing_home_and_no_battery(tmp_path: Path) -> None:
    s = HardwareProbe(proc_root=tmp_path / "x", home=tmp_path / "nope", ps=FakePs()).snapshot()
    assert s.on_battery is None and s.psi_cpu is None


def test_probe_ps_without_optional_apis(tmp_path: Path) -> None:
    ps = FakePs()
    ps.getloadavg = lambda: (_ for _ in ()).throw(OSError())  # type: ignore[method-assign]
    ps.sensors_battery = lambda: (_ for _ in ()).throw(NotImplementedError())  # type: ignore[method-assign]
    s = HardwareProbe(proc_root=tmp_path, home=tmp_path, ps=ps).snapshot()
    assert s.load1 == 0.0 and s.on_battery is None


def test_probe_real_psutil(tmp_path: Path) -> None:
    s = HardwareProbe(home=tmp_path).snapshot()
    assert s.mem_total_mb > 0 and s.cpu_count >= 1


def test_read_psi_garbage(tmp_path: Path) -> None:
    p = tmp_path / "f"
    p.write_text("lixo")
    assert read_psi(p) is None


def test_choose_profile() -> None:
    assert choose_profile(snap(mem_total_mb=2048)) == "minimal"
    assert choose_profile(snap(cpu_count=2)) == "minimal"
    assert choose_profile(snap(disk_free_mb=100)) == "minimal"
    assert choose_profile(snap(on_battery=True, battery_percent=10)) == "minimal"
    assert choose_profile(snap(on_battery=True, battery_percent=80)) == "standard"
    assert choose_profile(snap(mem_total_mb=32768, cpu_count=16)) == "full"
    assert (
        choose_profile(snap(mem_total_mb=32768, cpu_count=16, on_battery=True, battery_percent=90))
        == "standard"
    )
    assert choose_profile(snap()) == "standard"
    assert choose_profile(snap(mem_total_mb=2048), "full") == "full"
    assert choose_profile(snap(mem_total_mb=32768, cpu_count=16), "minimal") == "minimal"


def test_profile_components() -> None:
    m, s, f = (PROFILE_COMPONENTS[k] for k in ("minimal", "standard", "full"))
    assert m == {"ipc", "scheduler", "notifier", "audit"}
    assert m < s < f and "embeddings" in f and "embeddings" not in s


class SeqProbe:
    def __init__(self, seq: list[HardwareSnapshot]) -> None:
        self.seq = seq
        self.i = 0

    def snapshot(self) -> HardwareSnapshot:
        s = self.seq[min(self.i, len(self.seq) - 1)]
        self.i += 1
        return s


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0

    def clock(self) -> float:
        return self.now

    async def sleep(self, s: float) -> None:
        self.now += s


async def test_wait_until_stable_after_n_good() -> None:
    ft = FakeTime()
    busy, calm = snap(cpu_percent=0.95), snap()
    r = await wait_until_stable(
        SeqProbe([busy, calm, calm, busy, calm, calm, calm]),  # type: ignore[arg-type]
        thresholds=PressureSettings(),
        max_wait_s=100,
        clock=ft.clock,
        sleep=ft.sleep,
    )
    assert r.stable and r.samples == 7


async def test_wait_until_stable_gives_up() -> None:
    ft = FakeTime()
    r = await wait_until_stable(
        SeqProbe([snap(psi_cpu=50.0)]),  # type: ignore[arg-type]
        thresholds=PressureSettings(),
        max_wait_s=12,
        clock=ft.clock,
        sleep=ft.sleep,
    )
    assert not r.stable and r.waited_s >= 12


async def test_wait_until_stable_mem_busy() -> None:
    ft = FakeTime()
    r = await wait_until_stable(
        SeqProbe([snap(mem_available_mb=100)]),  # type: ignore[arg-type]
        thresholds=PressureSettings(),
        max_wait_s=5,
        clock=ft.clock,
        sleep=ft.sleep,
    )
    assert not r.stable


# ---------------------------------------------------------------- registry
def comp(
    name: str, cost: Any = "medium", essential: bool = False, log: list[str] | None = None
) -> FunctionComponent:
    log = log if log is not None else []

    async def s() -> None:
        log.append(f"sleep:{name}")

    async def w() -> None:
        log.append(f"wake:{name}")

    return FunctionComponent(name, essential=essential, cost=cost, on_sleep=s, on_wake=w)


async def test_lazy_loaded_once_concurrently() -> None:
    reg = ComponentRegistry()
    calls = 0

    async def factory() -> Sleepable:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return comp("memory")

    reg.register_lazy("memory", factory)
    assert reg.state("memory") == "unloaded"
    a = await asyncio.gather(*(reg.acquire("memory") for _ in range(5)))
    assert calls == 1 and len({id(x) for x in a}) == 1
    assert reg.state("memory") == "awake" and reg.states() == {"memory": "awake"}


async def test_allowed_filter_and_unknown() -> None:
    reg = ComponentRegistry()
    reg.register(comp("embeddings"))
    reg.allowed = frozenset({"memory"})
    with pytest.raises(ComponentNotAllowed):
        await reg.acquire("embeddings")
    reg.allowed = None
    with pytest.raises(KeyError):
        await reg.acquire("nope")


def test_essential_coercion_error() -> None:
    reg = ComponentRegistry()
    with pytest.raises(ValueError):
        reg.register(comp("scheduler", essential=False))
    with pytest.raises(ValueError):
        reg.register_lazy("ipc", lambda: None)  # type: ignore[arg-type,return-value]


async def test_sleep_order_wake_and_essential() -> None:
    log: list[str] = []
    reg = ComponentRegistry()
    reg.register(comp("scheduler", "low", True, log))
    reg.register(comp("a", "low", False, log))
    reg.register(comp("b", "high", False, log))
    reg.register(comp("c", "medium", False, log))

    async def lazy() -> Sleepable:
        return comp("d", "high", False, log)

    reg.register_lazy("d", lazy)  # nunca carregado: nao dorme
    assert await reg.sleep_nonessential() == ["b", "c", "a"]
    assert await reg.sleep_nonessential() == []
    assert reg.state("scheduler") == "awake" and reg.state("b") == "asleep"
    await reg.acquire("c")  # acorda sob demanda
    assert reg.state("c") == "awake" and "wake:c" in log
    assert set(await reg.wake_all()) == {"a", "b"}
    assert "sleep:scheduler" not in log


async def test_function_component_without_callbacks() -> None:
    c = FunctionComponent("x")
    await c.sleep()
    await c.wake()
    assert isinstance(c, Sleepable)


# ---------------------------------------------------------------- pressure
class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_monitor(
    dwell: float = 0.0,
) -> tuple[PressureMonitor, ComponentRegistry, Clock, list[PressureSample]]:
    reg = ComponentRegistry()
    clk = Clock()
    box: list[PressureSample] = [PressureSample(cpu=0.1, mem=0.3)]
    mon = PressureMonitor(reg, PressureSettings(min_dwell_s=dwell), lambda: box[-1], clock=clk)
    return mon, reg, clk, box


async def test_external_spike_enters_and_sleeps() -> None:
    mon, reg, _, box = make_monitor()
    reg.register(comp("scheduler", "low", True))
    reg.register(comp("memory"))
    box.append(PressureSample(cpu=0.95, mem=0.3))
    assert await mon.tick() == "enter" and mon.state == "pressured"
    assert reg.state("memory") == "asleep" and reg.state("scheduler") == "awake"
    box.append(PressureSample(cpu=0.2, mem=0.3))
    assert await mon.tick() == "exit" and reg.state("memory") == "awake"
    assert [t[1] for t in mon.transitions] == ["enter", "exit"]


async def test_self_load_does_not_enter() -> None:
    mon, _, _, box = make_monitor()
    box.append(PressureSample(cpu=0.95, mem=0.95, self_cpu=0.5, self_mem=0.4))
    assert await mon.tick() is None and mon.state == "normal"


async def test_mem_and_psi_enter() -> None:
    mon, _, _, _ = make_monitor()
    assert mon.evaluate(PressureSample(cpu=0.1, mem=0.95)) == "enter"
    assert mon.evaluate(PressureSample(cpu=0.1, mem=0.1, psi=30.0)) == "enter"


async def test_hysteresis_no_oscillation() -> None:
    mon, reg, _, box = make_monitor()
    reg.register(comp("memory"))
    box.append(PressureSample(cpu=0.9, mem=0.3))
    await mon.tick()
    # entre exit (0.60) e enter (0.85): mantem pressured
    for cpu in (0.7, 0.8, 0.65, 0.84, 0.7, 0.62):
        box.append(PressureSample(cpu=cpu, mem=0.3))
        assert await mon.tick() is None
    assert mon.state == "pressured"
    # psi acima do exit impede saida
    box.append(PressureSample(cpu=0.1, mem=0.3, psi=10.0))
    assert await mon.tick() is None
    box.append(PressureSample(cpu=0.1, mem=0.3, psi=1.0))
    assert await mon.tick() == "exit"
    # no normal, valores entre os limiares nao entram
    for cpu in (0.7, 0.8, 0.84):
        box.append(PressureSample(cpu=cpu, mem=0.3))
        assert await mon.tick() is None
    assert len(mon.transitions) == 2


async def test_min_dwell() -> None:
    mon, _, clk, box = make_monitor(dwell=60)
    box.append(PressureSample(cpu=0.99, mem=0.3))
    assert await mon.tick() is None  # recem criado: dentro do dwell
    clk.now += 61
    assert await mon.tick() == "enter"
    box.append(PressureSample(cpu=0.1, mem=0.3))
    clk.now += 10
    assert await mon.tick() is None
    clk.now += 60
    assert await mon.tick() == "exit"


async def test_run_loop_stops() -> None:
    mon, _, _, _ = make_monitor()
    n = 0

    async def fake_sleep(_: float) -> None:
        nonlocal n
        n += 1
        if n == 3:
            mon.stop()

    await mon.run(fake_sleep)
    assert n == 3


def test_default_sampler_real(tmp_path: Path) -> None:
    s = default_sampler(psi_path=tmp_path / "none")()
    assert 0 <= s.cpu <= 1 and 0 <= s.mem <= 1 and s.psi is None and s.self_mem > 0


def test_no_gateway_imports() -> None:
    import orion.daemon.pressure as p
    import orion.daemon.probe as q
    import orion.daemon.service as r
    import orion.daemon.sleepable as s

    for mod in (p, q, r, s):
        tree = ast.parse(Path(mod.__file__ or "").read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("orion.gateway")
            elif isinstance(node, ast.Import):
                assert not any(a.name.startswith("orion.gateway") for a in node.names)


# ---------------------------------------------------------------- service
class FakeRunner:
    def __init__(self, fail_on: str | None = None, rc_for: dict[str, int] | None = None) -> None:
        self.calls: list[list[str]] = []
        self.fail_on = fail_on
        self.rc_for = rc_for or {}

    async def run(self, argv: list[str]) -> CommandResult:
        self.calls.append(argv)
        if self.fail_on and self.fail_on in argv:
            return CommandResult(returncode=1, stderr="boom")
        for k, rc in self.rc_for.items():
            if k in argv:
                return CommandResult(returncode=rc)
        return CommandResult(returncode=0)


def mgr(tmp_path: Path, runner: FakeRunner) -> ServiceManager:
    return ServiceManager(
        home=tmp_path / "home",
        unit_dir=tmp_path / "units",
        runner=runner,
        exec_start=["/bin/true", "daemon", "run"],
        user="tester",
    )


def test_render_unit() -> None:
    u = render_unit(
        ["/opt/my bin/orion", "daemon", "run"], environment={"A": "b c"}, memory_high="1G"
    )
    for needle in (
        "Nice=10",
        "CPUWeight=20",
        "IOWeight=20",
        "MemoryHigh=1G",
        "WantedBy=default.target",
        "Restart=on-failure",
        "ExecStart='/opt/my bin/orion' daemon run",
        "Environment='A=b c'",
    ):
        assert needle in u


async def test_install_enable_disable(tmp_path: Path) -> None:
    r = FakeRunner()
    m = mgr(tmp_path, r)
    other = tmp_path / "home" / "keep.db"
    other.parent.mkdir(parents=True)
    other.write_text("x")
    path = await m.install()
    assert path.exists() and path.stat().st_mode & 0o777 == 0o644
    assert r.calls == [["systemctl", "--user", "daemon-reload"]]
    r.calls.clear()
    await m.enable()
    assert r.calls == [["systemctl", "--user", "enable", UNIT_NAME]]
    r.calls.clear()
    await m.disable()  # sem marker: sem loginctl
    assert not path.exists() and other.exists()
    assert not any(c[0] == "loginctl" for c in r.calls)
    assert r.calls[0] == ["systemctl", "--user", "disable", "--now", UNIT_NAME]


async def test_enable_boot_and_disable_with_marker(tmp_path: Path) -> None:
    r = FakeRunner()
    m = mgr(tmp_path, r)
    other = tmp_path / "home" / "keep.db"
    other.parent.mkdir(parents=True)
    other.write_text("x")
    await m.enable(boot=True)  # instala sozinho
    assert m.unit_path.exists()
    assert ["loginctl", "enable-linger", "tester"] in r.calls
    marker = tmp_path / "home" / "daemon" / "linger_by_orion"
    assert marker.exists()
    st = await m.status()
    assert st["installed"] and st["linger_by_orion"]
    r.calls.clear()
    await m.disable()
    assert ["loginctl", "disable-linger", "tester"] in r.calls
    assert not marker.exists() and not m.unit_path.exists() and other.exists()


async def test_start_stop_status_and_errors(tmp_path: Path) -> None:
    r = FakeRunner(rc_for={"is-active": 3, "is-enabled": 1})
    m = mgr(tmp_path, r)
    await m.start()
    await m.stop()
    assert ["systemctl", "--user", "start", UNIT_NAME] in r.calls
    assert not await m.is_active() and not await m.is_enabled()
    assert (await m.status())["installed"] is False
    bad = mgr(tmp_path, FakeRunner(fail_on="start"))
    with pytest.raises(ServiceError, match="boom"):
        await bad.start()


async def test_subprocess_runner() -> None:
    res = await SubprocessRunner().run([sys.executable, "-c", "print('oi')"])
    assert res.returncode == 0 and res.stdout.strip() == "oi"
    miss = await SubprocessRunner().run(["/nao/existe/xyz"])
    assert miss.returncode == 127


@pytest.mark.skipif(shutil.which("systemd-analyze") is None, reason="systemd-analyze ausente")
async def test_real_systemd_analyze_verify(tmp_path: Path) -> None:
    m = ServiceManager(
        home=tmp_path / "home",
        unit_dir=tmp_path / "units",
        runner=FakeRunner(),
        exec_start=[sys.executable, "-m", "orion.cli", "daemon", "run"],
        user="tester",
    )
    await m.install()
    proc = subprocess.run(
        ["systemd-analyze", "--user", "verify", str(m.unit_path)], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    ok, _ = await m.verify()
    assert ok
