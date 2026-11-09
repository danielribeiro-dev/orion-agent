"""
O.R.I.O.N — Tool ``daemon_control`` (v0.5.0 Sprint 7, ADR-032)

Liga, desliga e consulta o daemon por conversa natural ("deixa o ORION sempre ligado").
ActionLevel LEVEL_3: SEMPRE passa pela confirmação do PEP (fora de ``FULLY_AUTO``), mesmo para
``status``, porque a mesma tool liga autostart e linger. Projeto não confiável não liga daemon.
Nunca é entregue a subagents.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from orion.daemon.control import ACTIONS, DaemonControlError, DaemonController, format_status
from orion.runtime.provider import RuntimeResult
from orion.runtime.tools.base import BaseTool


class DaemonControlTool(BaseTool):
    name = "daemon_control"
    description = (
        "Control the ORION background daemon (opt-in; off by default). Actions: 'status'; 'start' "
        "(run now, no autostart); 'stop'; 'restart'; 'enable' (start at login; boot=true also keeps "
        "it running without a login session via loginctl linger, only when the user explicitly asks); "
        "'disable' (stop and remove autostart; ~/.orion is kept); 'install' (write the systemd unit "
        "only). Use it only when the user asks to keep ORION running, scheduled or notifying."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": list(ACTIONS)},
            "boot": {"type": "boolean", "description": "With 'enable': start at boot (linger)."},
        },
        "required": ["action"],
    }

    def __init__(self, controller: Callable[[], DaemonController], trusted: Callable[[], bool]) -> None:
        self._controller = controller
        self._trusted = trusted

    async def run(self, **params: Any) -> RuntimeResult:
        action = str(params.get("action", "status"))
        if action != "status" and not self._trusted():
            return RuntimeResult.fail(
                "this project's settings are not trusted; the daemon can only be controlled after "
                "the user trusts the project (or from another directory)"
            )
        try:
            outcome = await self._controller().run(action, boot=bool(params.get("boot", False)))
        except DaemonControlError as exc:
            return RuntimeResult.fail(str(exc))
        except Exception as exc:  # systemctl ausente, sem sessão D-Bus etc.
            return RuntimeResult.fail(f"{action} failed: {exc}")
        if isinstance(outcome, dict):
            return RuntimeResult.ok("\n".join(format_status(outcome)), status=json.loads(json.dumps(outcome, default=str)))
        return RuntimeResult.ok(outcome)
