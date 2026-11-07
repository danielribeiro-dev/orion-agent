"""Comandos de memória e habilidades."""

from __future__ import annotations

from rich.text import Text

from orion.tui.commands.base import BaseSlashCommand, CommandContext, CommandResult
from orion.tui.panels import SphereRow, key_hints, render_memory


class LearnCommand(BaseSlashCommand):
    name = "/learn"
    description = "Destila a solução da sessão em uma SKILL.md reutilizável"
    usage = "/learn [nome]"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        name = args or "um nome curto em kebab-case"
        await context.session.run_turn(
            "Destile a solução desta sessão em uma skill reutilizável: escreva "
            f".orion/skills/<nome>/SKILL.md usando {name} como nome."
        )
        return CommandResult(success=True)


class MemoryCommand(BaseSlashCommand):
    name = "/memory"
    description = "Inspeciona as 5 Esferas Cognitivas"
    usage = "/memory"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        session = context.session
        persona = session.identity.get_identity().persona_name if session.identity else "—"
        try:
            from orion.runtime.environment import EnvironmentMonitor

            healthy = EnvironmentMonitor().snapshot().headroom_safe
            environment = "Saudável" if healthy else "Headroom baixo"
        except Exception:
            environment = "Indisponível"

        facts_total = facts_confirmed = 0
        if session.facts is not None:
            facts_total = session.facts.count()
            facts_confirmed = session.facts.count_confirmed()

        events = 0
        try:
            timeline = await session.open_timeline()
            try:
                events = await timeline.count_events()
            finally:
                await timeline.close()
        except Exception:
            pass

        home = "~/.orion"
        rows = [
            SphereRow("user_profile", "Ativa", session.status_bar.github_user or "—", f"{home}/profile.json"),
            SphereRow("system_identity", "Ativa", persona, "Imutável + persona.json"),
            SphereRow("system_environment", "Ativa", environment, "Headroom Guard (> 1.5GB)"),
            SphereRow(
                "project_decisions",
                "Ativa" if session.facts is not None else "Inativa",
                f"{facts_total} Fatos",
                f"CONFIRMED ({facts_confirmed}) / INFERRED ({facts_total - facts_confirmed})",
            ),
            SphereRow("timeline_episodic", "Ativa", f"{events} Eventos", f"{home}/timeline.db (WAL)"),
        ]
        context.console.print(render_memory(rows))
        context.console.print(key_hints(("/timeline", "Linha do Tempo"), ("/recall", "Buscar")))
        return CommandResult(success=True, data=rows)


class TimelineCommand(BaseSlashCommand):
    name = "/timeline"
    description = "Exibe os eventos recentes da linha do tempo"
    usage = "/timeline [quantidade]"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        if args and not args.isdigit():
            return CommandResult(success=False, output_message=f"Uso: {self.usage}")
        timeline = await context.session.open_timeline()
        try:
            records = await timeline.get_recent_history(limit=int(args or 15))
        finally:
            await timeline.close()
        if not records:
            return CommandResult(success=True, output_message="Linha do tempo vazia.")
        for record in records:
            _print_record(context, record)
        return CommandResult(success=True, data=records)


class RecallCommand(BaseSlashCommand):
    name = "/recall"
    description = "Busca fatos e eventos passados na memória"
    usage = "/recall <termo>"
    requires_args = True

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        session = context.session
        needle = args.lower()
        found = 0
        if session.facts is not None:
            for fact in session.facts.search(limit=200):
                if needle in fact.key.lower() or needle in fact.value.lower():
                    line = Text(no_wrap=True, overflow="ellipsis")
                    line.append("● ", style="accent_blue")
                    line.append(f"[{fact.status.value}] {fact.key}: ", style="text_dim")
                    line.append(fact.value, style="text_primary")
                    context.console.print(line)
                    found += 1
        timeline = await session.open_timeline()
        try:
            records = await timeline.search_lexical(args, limit=10)
        except Exception:
            records = []
        finally:
            await timeline.close()
        for record in records:
            _print_record(context, record)
        found += len(records)
        if not found:
            return CommandResult(success=True, output_message=f"Nada encontrado para “{args}”.")
        return CommandResult(success=True, data=found)


def _print_record(context: CommandContext, record: object) -> None:
    line = Text(no_wrap=True, overflow="ellipsis")
    line.append("› ", style="text_dim")
    line.append(f"{record.timestamp:%d/%m %H:%M} {record.event_type:<11} ", style="text_dim")  # type: ignore[attr-defined]
    line.append(" ".join(record.content.split()), style="text_primary")  # type: ignore[attr-defined]
    context.console.print(line)
