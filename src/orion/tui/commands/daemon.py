"""
O.R.I.O.N TUI — ``/daemon`` (v0.5.0 Sprint 7, ADR-032).

``/daemon`` ou ``/daemon status`` só lê. Toda ação que muda algo (start, stop, restart, enable,
disable, install) roda pela tool ``daemon_control``, então passa pelo PEP com o card de sempre e
pela checagem de projeto confiável. ``/daemon inbox`` lista as pendências; ``/daemon approve <id>``
e ``/daemon deny <id>`` respondem a uma aprovação (só não nucleares: nuclear nunca é remota).
"""

from __future__ import annotations

from orion.tui.commands.base import BaseSlashCommand, CommandContext, CommandResult

DAEMON_USAGE = (
    "/daemon [status|start|stop|restart|enable [--boot]|disable|install|inbox|approve <id>|deny <id>]"
)
_MUTATING = ("start", "stop", "restart", "enable", "disable", "install")


class DaemonCommand(BaseSlashCommand):
    name = "/daemon"
    description = "Daemon opt-in: status, ligar/desligar, autostart e Inbox de pendências"
    usage = DAEMON_USAGE

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        from orion.daemon.control import DaemonControlError, DaemonController, format_status

        session = context.session
        parts = args.split()
        action = parts[0] if parts else "status"
        controller = DaemonController(session.home)
        if action == "status":
            for line in format_status(await controller.status()):
                context.console.print(line, style="text_dim")
            return CommandResult(success=True)
        if action in _MUTATING:
            params: dict[str, object] = {"action": action}
            if action == "enable" and "--boot" in parts[1:]:
                params["boot"] = True
            ok = await session.run_tool("daemon_control", params)
            return CommandResult(success=bool(ok))
        try:
            if action == "inbox":
                items = await controller.inbox("pending")
                if not items:
                    return CommandResult(success=True, output_message="Inbox vazia.")
                for item in items:
                    actions = "/".join(a["id"] for a in item.get("actions") or [])
                    context.console.print(
                        f"● {item['id']} · {item['kind']} · {item['title']}" + (f" · {actions}" if actions else ""),
                        style="text_dim",
                    )
                return CommandResult(success=True)
            if action in ("approve", "deny") and len(parts) == 2:
                done = await controller.resolve(parts[1], "approve" if action == "approve" else "deny")
                if not done:
                    return CommandResult(success=False, output_message=f"{parts[1]} não está pendente.")
                return CommandResult(success=True, output_message=f"✔ {parts[1]}: {action}.")
        except DaemonControlError as exc:
            return CommandResult(success=False, output_message=str(exc))
        except (ConnectionError, OSError, TimeoutError):
            return CommandResult(success=False, output_message="daemon não está em execução.")
        return CommandResult(success=False, output_message=f"Uso: {DAEMON_USAGE}")
