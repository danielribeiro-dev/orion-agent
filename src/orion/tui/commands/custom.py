"""Comandos custom: arquivos ``.md`` que viram slash commands.

Locais (o primeiro que define um nome vence): ``<ws>/.orion/commands`` (projeto),
``~/.orion/commands`` (user) e ``commands/`` de cada plugin (namespace
``/<plugin>:<comando>``). ``team/deploy.md`` vira ``/team:deploy``.

Frontmatter opcional: ``description``, ``argument-hint``, ``allowed-tools``.
No corpo, ``$ARGUMENTS`` recebe tudo o que o Senhor digitou depois do comando e
``$1``..``$9`` os argumentos posicionais. O comando apenas envia o prompt
renderizado ao agente: ele não executa nada por conta própria e toda tool
continua passando pelo PEP. Nomes de comandos nativos são reservados.
"""

from __future__ import annotations

import logging
import re
import shlex
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from orion.tui.commands.base import BaseSlashCommand, CommandContext, CommandResult

logger = logging.getLogger(__name__)

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
_NAME_PART = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_POSITIONAL = re.compile(r"\$([1-9])")


@dataclass(frozen=True)
class CustomCommandSpec:
    """Um comando custom carregado de disco."""

    name: str  # com a barra, ex.: "/fix-issue"
    description: str
    body: str
    source: str  # "project" | "user" | "plugin"
    path: Path
    argument_hint: str = ""
    allowed_tools: tuple[str, ...] = ()


def render_body(body: str, args: str) -> str:
    """Substitui ``$ARGUMENTS`` e ``$1..$9``; sem marcador, anexa os argumentos ao fim."""
    try:
        parts = shlex.split(args)
    except ValueError:
        parts = args.split()
    uses_marker = "$ARGUMENTS" in body or bool(_POSITIONAL.search(body))
    rendered = _POSITIONAL.sub(
        lambda m: parts[int(m.group(1)) - 1] if int(m.group(1)) <= len(parts) else "", body
    )
    rendered = rendered.replace("$ARGUMENTS", args)
    if args and not uses_marker:
        rendered = f"{rendered.rstrip()}\n\nARGUMENTS: {args}"
    return rendered.strip()


def _parse(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_text(encoding="utf-8")
    found = _FRONTMATTER.match(raw)
    if not found:
        return {}, raw.strip()
    meta = yaml.safe_load(found.group(1)) or {}
    if not isinstance(meta, dict):
        raise ValueError("frontmatter deve ser um mapa YAML")
    return meta, found.group(2).strip()


def _command_name(root: Path, file: Path, prefix: str) -> str | None:
    parts = [*file.relative_to(root).parent.parts, file.stem]
    if not all(_NAME_PART.match(p) for p in parts):
        return None
    return "/" + prefix + ":".join(parts)


def _scan(root: Path, source: str, prefix: str = "") -> Iterable[CustomCommandSpec]:
    if not root.is_dir():
        return
    for file in sorted(root.rglob("*.md")):
        name = _command_name(root, file, prefix)
        if name is None:
            logger.warning("comando custom ignorado (nome inválido): %s", file)
            continue
        try:
            meta, body = _parse(file)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            logger.warning("comando custom inválido em %s: %s", file, exc)
            continue
        if not body:
            continue
        tools = meta.get("allowed-tools") or meta.get("allowed_tools") or ()
        if isinstance(tools, str):
            tools = [t for t in re.split(r"[,\s]+", tools) if t]
        yield CustomCommandSpec(
            name=name,
            description=str(meta.get("description") or f"Comando custom ({source})"),
            body=body,
            source=source,
            path=file,
            argument_hint=str(meta.get("argument-hint") or meta.get("argument_hint") or ""),
            allowed_tools=tuple(str(t) for t in tools),
        )


def load_custom_commands(
    home: Path,
    workspace: Path,
    plugins: Iterable[Any] = (),
    reserved: Iterable[str] = (),
) -> list[CustomCommandSpec]:
    """Carrega os comandos custom; projeto > user > plugin; nativos são reservados."""
    taken = set(reserved)
    found: list[CustomCommandSpec] = []
    sources = [
        _scan(workspace / ".orion" / "commands", "project"),
        _scan(home / "commands", "user"),
    ]
    sources.extend(_scan(p.commands_dir, "plugin", prefix=f"{p.name}:") for p in plugins)
    for stream in sources:
        for spec in stream:
            if spec.name in taken:
                logger.warning("comando custom %s ignorado: nome já em uso (%s)", spec.name, spec.path)
                continue
            taken.add(spec.name)
            found.append(spec)
    return found


class CustomCommand(BaseSlashCommand):
    """Comando custom: renderiza o corpo e o envia como turno do agente.

    Não define ``name`` no nível da classe de propósito: o registry só
    descobre subclasses nomeadas, e estas são registradas por instância.
    """

    def __init__(self, spec: CustomCommandSpec) -> None:
        self.spec = spec
        self.name = spec.name  # type: ignore[misc]
        self.description = spec.description  # type: ignore[misc]
        self.usage = f"{spec.name} {spec.argument_hint}".strip()  # type: ignore[misc]

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        await context.session.run_turn(render_body(self.spec.body, args))
        return CommandResult(success=True)


def register_custom_commands(registry: Any, specs: Iterable[CustomCommandSpec]) -> int:
    """Registra no *registry* os comandos custom; devolve quantos entraram."""
    count = 0
    for spec in specs:
        registry.register(CustomCommand(spec))
        count += 1
    return count
