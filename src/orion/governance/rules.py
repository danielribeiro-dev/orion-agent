"""Regras de permissão declarativas (allow / ask / deny) avaliadas pelo PEP.

Formato de texto: ``Tool`` ou ``Tool(padrão)``.

* ``run_command(git status:*)``: prefixo com fronteira de palavra.
* ``run_command(npm test)``: comando exato.
* ``write_file(src/**)``: caminho (glob) ancorado no workspace.
* ``mcp__srv__*``: qualquer tool cujo nome case com o glob.

Precedência: **deny > ask > allow**. Regras ``allow`` nunca casam comandos
compostos (``;``, ``&&``, ``|``, redirecionamentos, substituições), para que
``git status:*`` não autorize ``git status && rm -rf x``. Regras ``deny`` e
``ask`` casam se *qualquer* trecho do comando casar.
"""

from __future__ import annotations

import fnmatch
import os
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

Effect = Literal["allow", "deny", "ask"]
_EFFECT_ORDER: dict[str, int] = {"deny": 0, "ask": 1, "allow": 2}

_COMMAND_TOOLS = frozenset({"run_command"})
_PATH_TOOLS = frozenset(
    {"read_file", "write_file", "edit_file", "notebook_edit", "glob", "grep", "search_files"}
)
_URL_TOOLS = frozenset({"web_fetch"})

_RULE_RE = re.compile(r"^\s*([^()\s]+)\s*(?:\((.*)\))?\s*$", re.DOTALL)
_SEGMENT_SPLIT = re.compile(r"&&|\|\||[;|&\n]")
_COMPLEX = re.compile(r"`|\$\(|<\(|>\(|[<>]|&&|\|\||[;|&\n]")


class PermissionRule(BaseModel):
    """Uma regra declarativa."""

    effect: Effect
    tool: str
    pattern: str | None = None

    def __str__(self) -> str:
        return f"{self.tool}({self.pattern})" if self.pattern is not None else self.tool


@dataclass(frozen=True)
class RuleMatch:
    """Regra vencedora para uma ação."""

    rule: PermissionRule

    @property
    def effect(self) -> Effect:
        return self.rule.effect


def parse_rule(effect: Effect, text: str) -> PermissionRule | None:
    """Converte ``Tool(padrão)`` em regra; ``None`` se o texto for inválido."""
    found = _RULE_RE.match(text)
    if not found:
        return None
    tool, pattern = found.group(1), found.group(2)
    return PermissionRule(effect=effect, tool=tool, pattern=pattern if pattern else None)


def rule_text_for(action_tool: str, params: dict[str, Any]) -> str:
    """Regra exata (``Tool(valor)``) que descreve esta ação, para "sempre permitir"."""
    subject = _subject(action_tool, params)
    return f"{action_tool}({subject})" if subject else action_tool


def _subject(tool: str, params: dict[str, Any]) -> str | None:
    if tool in _COMMAND_TOOLS:
        value = params.get("command")
    elif tool in _PATH_TOOLS:
        value = params.get("path") or params.get("file_path")
    elif tool in _URL_TOOLS:
        value = params.get("url")
    else:
        return None
    return str(value) if value else None


def command_segments(command: str) -> list[str]:
    """Divide um comando em trechos por operadores de controle do shell."""
    return [part.strip() for part in _SEGMENT_SPLIT.split(command) if part.strip()]


def is_complex_command(command: str) -> bool:
    """Verdadeiro se o comando encadeia, redireciona ou substitui comandos."""
    return bool(_COMPLEX.search(command))


def _command_matches(pattern: str, segment: str) -> bool:
    if pattern.endswith(":*"):
        prefix = pattern[:-2]
        return segment == prefix or segment.startswith(prefix + " ")
    if any(ch in pattern for ch in "*?["):
        return fnmatch.fnmatchcase(segment, pattern)
    return segment == pattern


def _expand(path: str) -> str:
    return os.path.expanduser(path)


def _path_candidates(raw: str, roots: Sequence[Path]) -> list[str]:
    expanded = _expand(raw)
    candidates = {raw, expanded}
    try:
        resolved = Path(expanded).resolve()
        candidates.add(str(resolved))
        for root in roots:
            try:
                candidates.add(str(resolved.relative_to(root)))
            except ValueError:
                continue
    except (OSError, RuntimeError):
        pass
    return list(candidates)


def _path_matches(pattern: str, raw: str, roots: Sequence[Path], *, liberal: bool) -> bool:
    pattern = _expand(pattern)
    candidates = _path_candidates(raw, roots)
    anchored = pattern.startswith(("/", "**"))
    if not anchored and not liberal:
        # allow: padrão relativo só vale dentro de algum root do workspace
        return any(
            fnmatch.fnmatchcase(c, pattern) for c in candidates if not Path(c).is_absolute()
        )
    for candidate in candidates:
        if fnmatch.fnmatchcase(candidate, pattern):
            return True
        if liberal and not anchored and fnmatch.fnmatchcase(candidate, "*/" + pattern):
            return True
    return False


class RuleSet:
    """Conjunto imutável de regras com avaliação por precedência."""

    def __init__(self, rules: Iterable[PermissionRule] = ()) -> None:
        self._rules = tuple(sorted(rules, key=lambda r: _EFFECT_ORDER[r.effect]))

    def __len__(self) -> int:
        return len(self._rules)

    @property
    def rules(self) -> tuple[PermissionRule, ...]:
        return self._rules

    @classmethod
    def from_lists(
        cls, *, allow: Iterable[str] = (), deny: Iterable[str] = (), ask: Iterable[str] = ()
    ) -> RuleSet:
        rules: list[PermissionRule] = []
        for effect, texts in (("allow", allow), ("deny", deny), ("ask", ask)):
            for text in texts:
                parsed = parse_rule(effect, text)  # type: ignore[arg-type]
                if parsed is not None:
                    rules.append(parsed)
        return cls(rules)

    def match(
        self, tool: str, params: dict[str, Any], roots: Sequence[Path] = ()
    ) -> RuleMatch | None:
        """Devolve a regra vencedora (deny > ask > allow) ou ``None``."""
        for rule in self._rules:
            if self._matches(rule, tool, params, roots):
                return RuleMatch(rule)
        return None

    def allows_outside(self, tool: str, params: dict[str, Any], roots: Sequence[Path]) -> bool:
        """``allow`` explícito com padrão absoluto cobre um caminho fora do workspace."""
        match = self.match(tool, params, roots)
        if match is None or match.effect != "allow":
            return False
        pattern = match.rule.pattern or ""
        return _expand(pattern).startswith("/")

    @staticmethod
    def _matches(
        rule: PermissionRule, tool: str, params: dict[str, Any], roots: Sequence[Path]
    ) -> bool:
        if not fnmatch.fnmatchcase(tool, rule.tool):
            return False
        if rule.pattern is None:
            return True
        subject = _subject(tool, params)
        if subject is None:
            return False
        if tool in _COMMAND_TOOLS:
            if rule.effect == "allow":
                return not is_complex_command(subject) and _command_matches(
                    rule.pattern, subject.strip()
                )
            parts = command_segments(subject) or [subject.strip()]
            return any(_command_matches(rule.pattern, part) for part in parts) or _command_matches(
                rule.pattern, subject.strip()
            )
        if tool in _PATH_TOOLS:
            return _path_matches(rule.pattern, subject, roots, liberal=rule.effect != "allow")
        return fnmatch.fnmatchcase(subject, rule.pattern)
