"""Componentes adormecíveis do daemon e seu registro (ADR-035).

Essenciais (``ipc``, ``scheduler``, ``audit``) nunca dormem. Os demais carregam sob demanda e
podem ser postos para dormir sob pressão. Determinístico, zero token.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Literal, Protocol, runtime_checkable

Cost = Literal["low", "medium", "high"]
ComponentState = Literal["unloaded", "awake", "asleep"]
ESSENTIAL: frozenset[str] = frozenset({"ipc", "scheduler", "audit"})

_COST_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2}


class ComponentNotAllowed(Exception):
    """Componente fora do perfil de boot ativo."""


@runtime_checkable
class Sleepable(Protocol):
    """Contrato de um componente que pode dormir e acordar."""

    name: str
    essential: bool
    cost: Cost

    async def sleep(self) -> None: ...

    async def wake(self) -> None: ...


class FunctionComponent:
    """Adaptador: monta um :class:`Sleepable` a partir de callables assíncronos."""

    def __init__(
        self,
        name: str,
        *,
        essential: bool = False,
        cost: Cost = "medium",
        on_sleep: Callable[[], Awaitable[None]] | None = None,
        on_wake: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.name = name
        self.essential = essential
        self.cost: Cost = cost
        self._on_sleep = on_sleep
        self._on_wake = on_wake

    async def sleep(self) -> None:
        if self._on_sleep is not None:
            await self._on_sleep()

    async def wake(self) -> None:
        if self._on_wake is not None:
            await self._on_wake()


class _Entry:
    def __init__(
        self,
        name: str,
        factory: Callable[[], Awaitable[Sleepable]] | None,
        essential: bool,
        cost: Cost,
        instance: Sleepable | None = None,
    ) -> None:
        self.name = name
        self.factory = factory
        self.essential = essential
        self.cost = cost
        self.instance = instance
        self.asleep = False
        self.lock = asyncio.Lock()


class ComponentRegistry:
    """Registro com carga preguiçosa, filtro por perfil e sono seletivo."""

    def __init__(self) -> None:
        self._entries: dict[str, _Entry] = {}
        self.allowed: frozenset[str] | None = None

    @staticmethod
    def _check(name: str, essential: bool) -> None:
        if name in ESSENTIAL and not essential:
            raise ValueError(f"componente essencial '{name}' não pode ser não-essencial")

    def register(self, component: Sleepable) -> None:
        self._check(component.name, component.essential)
        self._entries[component.name] = _Entry(
            component.name, None, component.essential, component.cost, component
        )

    def register_lazy(
        self,
        name: str,
        factory: Callable[[], Awaitable[Sleepable]],
        *,
        essential: bool = False,
        cost: Cost = "medium",
    ) -> None:
        self._check(name, essential)
        self._entries[name] = _Entry(name, factory, essential, cost)

    async def acquire(self, name: str) -> Sleepable:
        if self.allowed is not None and name not in self.allowed:
            raise ComponentNotAllowed(name)
        entry = self._entries.get(name)
        if entry is None:
            raise KeyError(name)
        async with entry.lock:
            if entry.instance is None:
                assert entry.factory is not None
                entry.instance = await entry.factory()
            if entry.asleep:
                await entry.instance.wake()
                entry.asleep = False
            return entry.instance

    def state(self, name: str) -> ComponentState:
        entry = self._entries[name]
        if entry.instance is None:
            return "unloaded"
        return "asleep" if entry.asleep else "awake"

    def states(self) -> dict[str, ComponentState]:
        return {name: self.state(name) for name in self._entries}

    async def sleep_nonessential(self) -> list[str]:
        slept: list[str] = []
        candidates = sorted(self._entries.values(), key=lambda e: _COST_ORDER[e.cost])
        for entry in candidates:
            if entry.essential or entry.instance is None or entry.asleep:
                continue
            async with entry.lock:
                await entry.instance.sleep()
                entry.asleep = True
            slept.append(entry.name)
        return slept

    async def wake_all(self) -> list[str]:
        woken: list[str] = []
        for entry in self._entries.values():
            if entry.instance is None or not entry.asleep:
                continue
            async with entry.lock:
                await entry.instance.wake()
                entry.asleep = False
            woken.append(entry.name)
        return woken
