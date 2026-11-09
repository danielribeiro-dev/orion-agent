"""Agendador determinístico do ORION (Sprint 7): cron, intervalos e disparos únicos.

Espera ociosa não chama provedor algum (ADR-022): o agendador só dorme até o próximo horário
devido. Este pacote não faz I/O de rede nem acorda modelo; quem executa o disparo é a porta
``FirePort`` injetada pelo daemon.
"""

from __future__ import annotations

from orion.scheduler.cronspec import InvalidSpec, describe, next_fire, spec_kind, validate_spec
from orion.scheduler.runner import FireOutcome, FirePort, SchedulerRunner
from orion.scheduler.store import (
    MAX_SCHEDULES,
    Schedule,
    SchedulerLock,
    SchedulerLocked,
    ScheduleRun,
    ScheduleStore,
)

__all__ = [
    "MAX_SCHEDULES",
    "FireOutcome",
    "FirePort",
    "InvalidSpec",
    "Schedule",
    "ScheduleRun",
    "ScheduleStore",
    "SchedulerLock",
    "SchedulerLocked",
    "SchedulerRunner",
    "describe",
    "next_fire",
    "spec_kind",
    "validate_spec",
]
