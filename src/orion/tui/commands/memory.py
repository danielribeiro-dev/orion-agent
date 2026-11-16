"""Comandos de memória e habilidades."""

from __future__ import annotations

import asyncio
from pathlib import Path

from orion.memory.models import UserProfile
from orion.tui.commands.base import BaseSlashCommand, CommandContext, CommandResult
from orion.tui.memory_views import FactRow, FactsView, TimelineView, entries_from_records
from orion.tui.panels import SphereRow, key_hints, render_memory


class LearnCommand(BaseSlashCommand):
    name = "/learn"
    description = "Destila a solução da sessão em uma SKILL.md reutilizável"
    usage = "/learn [nome]"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        if not getattr(context.session, "history", None):
            # A-01: sem conversa não há solução a destilar; não gasta um turno do modelo
            return CommandResult(success=False, output_message="Nada a destilar ainda: /learn usa a conversa desta sessão.")
        name = args or "um nome curto em kebab-case"
        await context.session.run_turn(
            "Destile a solução desta sessão em uma skill reutilizável: escreva "
            f".orion/skills/<nome>/SKILL.md usando {name} como nome."
        )
        return CommandResult(success=True)


class MemoryCommand(BaseSlashCommand):
    name = "/memory"
    description = "Inspeciona as 5 Esferas Cognitivas"
    usage = "/memory [model [install]]"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        words = args.split()
        if words[:1] == ["model"]:
            return await self._model(words[1:], context)
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
        profile = _load_profile(session.home)
        inferred = facts_total - facts_confirmed
        rows = [
            # N-20: o perfil vem de ~/.orion, nunca do usuário do SO ou do git
            SphereRow("Perfil do Senhor", "Ativa", profile.call_sign, f"{home}/profile.json"),
            SphereRow("Identidade", "Ativa", persona, "origem imutável + persona"),
            SphereRow("Ambiente", "Ativa", environment, "folga de RAM > 1,5 GB"),
            SphereRow(
                "Decisões do projeto",
                "Ativa" if session.facts is not None else "Inativa",
                f"{facts_total} {'fato' if facts_total == 1 else 'fatos'}",
                f"{facts_confirmed} confirmados · {inferred} inferidos",
            ),
            SphereRow("Linha do tempo", "Ativa", f"{events} {'evento' if events == 1 else 'eventos'}", f"{home}/timeline.db"),
        ]
        context.console.print(render_memory(rows))
        context.console.print(key_hints(("/timeline", "linha do tempo"), ("/recall <termo>", "buscar")))
        return CommandResult(success=True, data=rows)


    async def _model(self, words: list[str], context: CommandContext) -> CommandResult:
        """Modelo de embeddings: estado ou instalação explícita (ADR-040: rede só com pedido)."""
        from orion.memory.vector_store import (
            EMBED_MODEL_SIZE_MB,
            default_model_cache,
            embedding_model_installed,
            install_embedding_model,
        )

        session = context.session
        cache = default_model_cache(session.home / "timeline.db")
        installed = await asyncio.to_thread(embedding_model_installed, cache)
        if words[:1] != ["install"]:
            state = "instalado" if installed else "não instalado (memória semântica desligada)"
            message = f"● Modelo de embeddings: {state} · {cache}"
            if not installed:
                message += f"\n  › /memory model install baixa ~{EMBED_MODEL_SIZE_MB} MB uma única vez."
            return CommandResult(success=True, output_message=message)
        if installed:
            return CommandResult(success=True, output_message="✔ Modelo de embeddings já instalado.")
        with context.console.status(
            f"Baixando o modelo de embeddings (~{EMBED_MODEL_SIZE_MB} MB)…", spinner="dots"
        ):
            try:
                await asyncio.to_thread(install_embedding_model, cache)
            except Exception as exc:  # noqa: BLE001 - rede/disco: mensagem, nunca traceback
                return CommandResult(success=False, output_message=f"✖ Falha ao baixar o modelo: {exc}")
        enable = getattr(session.recall, "enable_semantic", None)
        if callable(enable):
            enable()
        return CommandResult(success=True, output_message="✔ Modelo instalado. Memória semântica ligada.")


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
        limit = int(args or 15)
        context.console.print(
            TimelineView(
                entries_from_records(records),
                "Linha do tempo",
                footer=f"/timeline {limit * 3} mostra mais · /recall <termo> busca",
            )
        )
        return CommandResult(success=True, data=records)


class RecallCommand(BaseSlashCommand):
    name = "/recall"
    description = "Busca fatos e eventos passados na memória"
    usage = "/recall <termo>"
    requires_args = True

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        session = context.session
        needle = args.lower()
        facts: list[FactRow] = []
        if session.facts is not None:
            for fact in session.facts.search(limit=200):
                if needle in fact.key.lower() or needle in fact.value.lower():
                    facts.append(FactRow(fact.key, fact.value, str(fact.status.value)))
        timeline = await session.open_timeline()
        try:
            records = await timeline.search_lexical(args, limit=10)
        except Exception:
            records = []
        finally:
            await timeline.close()
        if facts:
            context.console.print(FactsView(facts, highlight=args))
        if records:
            context.console.print(TimelineView(entries_from_records(records), "Episódios", highlight=args))
        found = len(facts) + len(records)
        if not found:
            return CommandResult(success=True, output_message=f"Nada encontrado para “{args}”.")
        return CommandResult(success=True, data=found)


def _load_profile(home: Path) -> UserProfile:
    """Perfil do Senhor em ``~/.orion/profile.json``; sem arquivo, o padrão (``Senhor``)."""
    try:
        return UserProfile.model_validate_json((home / "profile.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return UserProfile()
