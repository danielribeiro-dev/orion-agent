"""Métricas de cadência a partir da linha do tempo de amostras do ``LabTerminal``."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from tests.lab.pty_driver import Sample

BASELINE = Path(__file__).with_name("baseline.json")


@dataclass
class Probe:
    first_char_s: float | None
    total_s: float
    updates_per_s: float
    max_gap_after_first_s: float
    cpu_core_pct: float


def changes(samples: list[Sample], start: float, end: float) -> list[float]:
    """Instantes em que a tela mudou dentro da janela [start, end]."""
    out: list[float] = []
    last = ""
    for sample in samples:
        if start <= sample.t <= end and sample.digest != last:
            out.append(sample.t)
        last = sample.digest
    return out


def measure(
    samples: list[Sample], sent_at: float, first_char_at: float | None, done_at: float, cpu_s: float
) -> Probe:
    total = done_at - sent_at
    moments = changes(samples, first_char_at or sent_at, done_at)
    gaps = [b - a for a, b in zip(moments, moments[1:], strict=False)]
    streaming = max(done_at - (first_char_at or sent_at), 1e-6)
    return Probe(
        first_char_s=None if first_char_at is None else round(first_char_at - sent_at, 2),
        total_s=round(total, 2),
        updates_per_s=round(len(moments) / streaming, 1),
        max_gap_after_first_s=round(max(gaps), 2) if gaps else 0.0,
        cpu_core_pct=round(100 * cpu_s / max(total, 1e-6), 1),
    )


def load_baseline() -> dict[str, dict[str, float]]:
    if not BASELINE.exists():
        return {}
    data: dict[str, dict[str, float]] = json.loads(BASELINE.read_text(encoding="utf-8"))
    return data


def record(name: str, probe: Probe) -> None:
    """Grava a métrica como baseline (use ``ORION_LAB_RECORD=1``)."""
    data = load_baseline()
    data[name] = asdict(probe)
    BASELINE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
