"""Controle do daemon a partir da CLI, do ``/daemon`` e da tool ``daemon_control`` (ADR-032).

Opt-in em níveis independentes:

* ``install`` grava a unit do ``systemd --user`` (não liga nada);
* ``start`` liga agora (marca ``daemon.enabled``), sem autostart;
* ``enable`` sobe no login; ``enable --boot`` acrescenta ``loginctl enable-linger`` explícito;
* ``disable`` para, remove a unit, desfaz o linger que o ORION ligou e desliga ``daemon.enabled``,
  preservando ``~/.orion/``.

Só a camada do usuário (``~/.orion/settings.json``) guarda ``daemon``: um projeto nunca liga o daemon.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from orion.daemon import ipc
from orion.daemon.client import DaemonClient, DaemonUnavailable, call_once
from orion.daemon.service import ServiceManager
from orion.settings.io import read_json_object
from orion.settings.loader import save_user_settings, user_settings_path
from orion.settings.models import DaemonSettings

ACTIONS = ("status", "start", "stop", "enable", "disable", "install", "restart")


class DaemonControlError(RuntimeError):
    """Pedido de controle que não pode ser atendido (mensagem para o Senhor)."""


class DaemonController:
    def __init__(
        self,
        home: Path,
        *,
        service: ServiceManager | None = None,
        socket: Path | None = None,
    ) -> None:
        self.home = home
        self.service = service or ServiceManager(home=home)
        self.socket = socket or ipc.socket_path(home)

    # ------------------------------------------------------------------
    # Settings (camada do usuário)
    # ------------------------------------------------------------------

    def settings(self) -> DaemonSettings:
        raw = (read_json_object(user_settings_path(self.home)) or {}).get("daemon")
        return DaemonSettings(**raw) if isinstance(raw, dict) else DaemonSettings()

    def _save(self, **updates: Any) -> DaemonSettings:
        raw = (read_json_object(user_settings_path(self.home)) or {}).get("daemon")
        current = dict(raw) if isinstance(raw, dict) else {}
        current.update(updates)
        merged = DaemonSettings(**current)  # valida antes de gravar
        save_user_settings(self.home, {"daemon": current})
        return merged

    # ------------------------------------------------------------------

    async def live_status(self) -> dict[str, Any] | None:
        try:
            result = await call_once(self.socket, "status", timeout_s=5.0)
        except (DaemonUnavailable, ipc.IpcError, TimeoutError):
            return None
        return result if isinstance(result, dict) else None

    async def status(self) -> dict[str, Any]:
        settings = self.settings()
        return {
            "enabled": settings.enabled,
            "autostart": settings.autostart,
            "service": await self.service.status(),
            "daemon": await self.live_status(),
        }

    async def install(self) -> str:
        path = await self.service.install()
        return f"Unit gravada em {path} (autostart continua desligado)."

    async def start(self) -> str:
        self._save(enabled=True)
        if not self.service.unit_path.exists():
            await self.service.install()
        await self.service.start()
        return "Daemon iniciado (sem autostart; use /daemon enable para subir no login)."

    async def stop(self) -> str:
        if self.service.unit_path.exists():
            await self.service.stop()
            return "Daemon parado."
        try:
            await call_once(self.socket, "shutdown", timeout_s=5.0)
        except (DaemonUnavailable, ipc.IpcError, TimeoutError) as exc:
            raise DaemonControlError("nenhum daemon em execução") from exc
        return "Daemon parado."

    async def restart(self) -> str:
        await self.stop()
        return await self.start()

    async def enable(self, *, boot: bool = False) -> str:
        self._save(enabled=True, autostart="boot" if boot else "login")
        await self.service.enable(boot=boot)
        await self.service.start()
        when = "no boot (linger ligado explicitamente)" if boot else "no login"
        return f"Daemon ativo e configurado para subir {when}."

    async def disable(self) -> str:
        await self.service.disable()
        self._save(enabled=False, autostart="off")
        return "Daemon desligado: autostart removido, linger revertido; ~/.orion preservado."

    async def run(self, action: str, *, boot: bool = False) -> str | dict[str, Any]:
        if action not in ACTIONS:
            raise DaemonControlError(f"ação desconhecida: {action} (use {', '.join(ACTIONS)})")
        if action == "status":
            return await self.status()
        if action == "enable":
            return await self.enable(boot=boot)
        handler = getattr(self, action)
        result: str = await handler()
        return result

    # ------------------------------------------------------------------
    # Inbox
    # ------------------------------------------------------------------

    async def inbox(self, status: str | None = "pending") -> list[dict[str, Any]]:
        try:
            items = await call_once(self.socket, "inbox.list", {"status": status} if status else {})
        except (DaemonUnavailable, ipc.IpcError, TimeoutError) as exc:
            raise DaemonControlError("daemon não está em execução") from exc
        return list(items or [])

    async def resolve(self, item_id: str, action: str) -> bool:
        async with DaemonClient(self.socket, timeout_s=5.0) as client:
            outcome = await client.call("inbox.resolve", {"id": item_id, "action": action})
        return bool(outcome and outcome.get("resolved"))


def format_status(status: dict[str, Any]) -> list[str]:
    """Linhas de ``/daemon status`` (glifos permitidos, sem emojis)."""
    service = status.get("service") or {}
    live = status.get("daemon")
    state = "● ativo" if live else "· parado"
    lines = [
        f"{state} · opt-in {'ligado' if status.get('enabled') else 'desligado'} · autostart {status.get('autostart')}",
        f"unit {'instalada' if service.get('installed') else 'ausente'} · "
        f"systemd {'habilitado' if service.get('enabled') else 'desabilitado'} · "
        f"linger pelo ORION {'sim' if service.get('linger_by_orion') else 'não'}",
    ]
    if live:
        lines.append(
            f"perfil {live.get('profile')} · pressão {live.get('pressure')} · agendas {live.get('schedules')} · "
            f"inbox {live.get('inbox_pending')} · clientes {live.get('clients')} · "
            f"chamadas ao provider {live.get('provider_calls')}"
            + (" · silêncio" if live.get("quiet") else "")
        )
        components = live.get("components") or {}
        if components:
            lines.append("componentes " + " · ".join(f"{k} {v}" for k, v in sorted(components.items())))
    return lines
