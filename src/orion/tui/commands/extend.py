"""Comandos de extensibilidade: /skills."""

from __future__ import annotations

from rich.table import Table
from rich.text import Text

from orion.tui.commands.base import BaseSlashCommand, CommandContext, CommandResult
from orion.tui.panels import brand_title, orion_panel


class SkillsCommand(BaseSlashCommand):
    name = "/skills"
    description = "Lista as skills disponíveis ou ativa uma pelo nome"
    usage = "/skills [nome [pedido]]"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        engine = getattr(context.session, "skills", None)
        if engine is None:
            return CommandResult(success=False, output_message="Skills indisponíveis nesta sessão.")
        engine.reload()
        skills = engine.discovered_skills
        name, _, request = args.strip().partition(" ")
        if name:
            if name not in skills:
                return CommandResult(success=False, output_message=f"Skill desconhecida: {name}.")
            prompt = f"Use a skill '{name}' (via use_skill)" + (f" para: {request.strip()}" if request.strip() else ".")
            await context.session.run_turn(prompt)
            return CommandResult(success=True)
        if not skills:
            return CommandResult(success=True, output_message="Nenhuma skill encontrada.")
        table = Table.grid(padding=(0, 2))
        table.add_column(no_wrap=True)
        table.add_column(no_wrap=True)
        table.add_column()
        for skill in sorted(skills.values(), key=lambda b: b.metadata.name):
            table.add_row(
                Text(skill.metadata.name, style="accent_cyan"),
                Text(skill.source, style="text_dim"),
                Text(skill.metadata.description, style="text_primary"),
            )
        context.console.print(orion_panel(table, brand_title("Skills")))
        return CommandResult(success=True)
