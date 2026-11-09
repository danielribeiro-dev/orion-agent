"""
O.R.I.O.N TUI — Intelligent Autocomplete & Mention Resolution Engine.

Implements prompt_toolkit completers for Slash Commands (/) and Workspace Files (@),
with robust .gitignore parsing, fuzzy filtering, and security-hardened path resolution.
"""

from __future__ import annotations

import fnmatch
import os
import re
import time
from collections.abc import Callable, Iterable
from pathlib import Path

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

# ---------------------------------------------------------------------------
# Default directories and patterns to always ignore
# ---------------------------------------------------------------------------

DEFAULT_IGNORED_DIRS: set[str] = {
    ".git",
    ".venv",
    "venv",
    "ENV",
    "env",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".cache",
    ".coverage",
    ".idea",
    ".vscode",
    ".token-optimizer",
    "build",
    "dist",
    "eggs",
    ".eggs",
}

DEFAULT_IGNORED_PATTERNS: list[str] = [
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.so",
    "*.dylib",
    "*.dll",
    "*.swp",
    "*.swo",
    "*~",
    ".DS_Store",
    "*.coverage*",
    "*.egg-info",
]


# ---------------------------------------------------------------------------
# Slash Commands Catalog Metadata
# ---------------------------------------------------------------------------


class SlashCommandInfo:
    """Metadados de um comando slash suportado pelo ORION."""

    def __init__(
        self,
        name: str,
        description: str,
        icon: str = "",
        category: str = "general",
    ) -> None:
        self.name = name if name.startswith("/") else f"/{name}"
        self.description = description
        self.icon = icon
        self.category = category

    def __repr__(self) -> str:
        return f"<SlashCommandInfo {self.name}: {self.description}>"


OFFICIAL_SLASH_COMMANDS: list[SlashCommandInfo] = [
    SlashCommandInfo(
        "/skills",
        "Listar skills ou ativar uma pelo nome",
        icon="●",
        category="memory",
    ),
    # Cognitivos & Raciocínio
    SlashCommandInfo(
        "/plan",
        "Gerar plano estruturado de execução antes da implementação",
        icon="❯",
        category="cognitive",
    ),
    SlashCommandInfo(
        "/goal",
        "Modo de execução autônoma contínua até conclusão",
        icon="❯",
        category="cognitive",
    ),
    SlashCommandInfo(
        "/grill-me",
        "Entrevista investigativa para alinhar e refinar decisões",
        icon="❯",
        category="cognitive",
    ),
    SlashCommandInfo(
        "/review",
        "Revisão rigorosa de código e conformidade com padrões",
        icon="❯",
        category="cognitive",
    ),
    # Memória & Habilidades
    SlashCommandInfo(
        "/learn",
        "Auto-destilação: compilar solução em nova skill SKILL.md",
        icon="●",
        category="memory",
    ),
    SlashCommandInfo(
        "/memory",
        "Inspecionar e gerenciar fatos da memória tríplice",
        icon="●",
        category="memory",
    ),
    SlashCommandInfo(
        "/timeline",
        "Visualizar linha do tempo contínua no SQLite WAL",
        icon="●",
        category="memory",
    ),
    SlashCommandInfo(
        "/recall",
        "Busca profunda híbrida RRF em episódios e memórias",
        icon="●",
        category="memory",
    ),
    # Contexto & Branches
    SlashCommandInfo(
        "/compact",
        "Compactar histórico de conversa liberando contexto",
        icon="›",
        category="context",
    ),
    SlashCommandInfo(
        "/context",
        "Exibir uso de tokens e detalhamento de contexto atual",
        icon="›",
        category="context",
    ),
    SlashCommandInfo(
        "/branch",
        "Criar novo workspace isolado em branch",
        icon="›",
        category="context",
    ),
    SlashCommandInfo(
        "/merge",
        "Integrar alterações do branch ativo à Main Timeline",
        icon="›",
        category="context",
    ),
    # Operação & Governança
    SlashCommandInfo(
        "/diff",
        "Visualizar alterações e diffs pendentes no workspace",
        icon="❯",
        category="operation",
    ),
    SlashCommandInfo(
        "/undo",
        "Reverter últimas alterações ou turno anterior",
        icon="❯",
        category="operation",
    ),
    SlashCommandInfo(
        "/resume",
        "Listar ou retomar sessões anteriores deste workspace",
        icon="❯",
        category="operation",
    ),
    SlashCommandInfo(
        "/rewind",
        "Voltar conversa e arquivos para antes de um pedido",
        icon="❯",
        category="operation",
    ),
    SlashCommandInfo(
        "/run",
        "Executar comando ou script com governança PEP",
        icon="❯",
        category="operation",
    ),
    SlashCommandInfo(
        "/doctor",
        "Diagnóstico de integridade do ambiente e dependências",
        icon="❯",
        category="operation",
    ),
    SlashCommandInfo(
        "/cost",
        "Relatório financeiro de custos e consumo acumulado (USD/BRL)",
        icon="❯",
        category="operation",
    ),
    SlashCommandInfo(
        "/config",
        "Inspecionar e alterar configurações do ORION",
        icon="❯",
        category="operation",
    ),
    SlashCommandInfo(
        "/model",
        "Selecionar o modelo de IA ativo",
        icon="❯",
        category="operation",
    ),
    SlashCommandInfo(
        "/mcp",
        "Gerenciar conexões e ferramentas do Model Context Protocol",
        icon="❯",
        category="operation",
    ),
    SlashCommandInfo(
        "/agents",
        "Listar subagents, ver execuções e confiar nos agentes do projeto",
        icon="❯",
        category="operation",
    ),
    SlashCommandInfo(
        "/tasks",
        "Tasks e shells em segundo plano: listar, ver resultado e cancelar",
        icon="❯",
        category="operation",
    ),
    SlashCommandInfo(
        "/loop",
        "Verificação recorrente em segundo plano, com triagem antes de gastar tokens",
        icon="❯",
        category="operation",
    ),
    SlashCommandInfo(
        "/daemon",
        "Daemon opt-in: status, ligar/desligar, autostart e Inbox de pendências",
        icon="❯",
        category="operation",
    ),
    SlashCommandInfo(
        "/voice",
        "Ativar ou silenciar o daemon de voz e presença ambiente",
        icon="❯",
        category="operation",
    ),
    SlashCommandInfo(
        "/clear",
        "Limpar terminal preservando estado da sessão",
        icon="❯",
        category="operation",
    ),
    SlashCommandInfo(
        "/help",
        "Exibir ajuda detalhada e lista de comandos disponíveis",
        icon="❯",
        category="operation",
    ),
]


# ---------------------------------------------------------------------------
# GitIgnore Matcher
# ---------------------------------------------------------------------------


class GitIgnoreMatcher:
    """Motor leve e resiliente de filtragem baseado em padrões .gitignore."""

    def __init__(self, workspace_root: Path | str | None = None) -> None:
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd()
        self.rules: list[tuple[str, bool]] = []  # (pattern, is_dir_only)
        self.ignored_dirs: set[str] = set(DEFAULT_IGNORED_DIRS)
        self.load_gitignore()

    def load_gitignore(self) -> None:
        """Carrega e compila as regras do arquivo .gitignore do workspace."""
        gitignore_path = self.workspace_root / ".gitignore"
        if not gitignore_path.is_file():
            return

        try:
            with open(gitignore_path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    # Diretório restrito (termina com /)
                    is_dir_only = line.endswith("/")
                    pattern = line.rstrip("/")

                    # Remove prefixo de âncora inicial para facilitar match
                    if pattern.startswith("/"):
                        pattern = pattern[1:]

                    self.rules.append((pattern, is_dir_only))
                    if is_dir_only and "/" not in pattern:
                        self.ignored_dirs.add(pattern)
        except Exception:
            pass

    def is_ignored(self, path: Path | str, is_dir: bool = False) -> bool:
        """Verifica se um caminho ou nome de arquivo/diretório deve ser ignorado."""
        if isinstance(path, str):
            rel_str = path
            name = os.path.basename(path)
        else:
            try:
                rel_str = str(path.relative_to(self.workspace_root)).replace("\\", "/")
            except ValueError:
                rel_str = path.name
            name = path.name

        # Checagem direta de pastas ignoradas
        if name in self.ignored_dirs:
            return True

        # Checagem de padrões default
        for pattern in DEFAULT_IGNORED_PATTERNS:
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel_str, pattern):
                return True

        # Checagem contra regras do .gitignore
        for pattern, dir_only in self.rules:
            if dir_only and not is_dir:
                continue

            # Casamento exato ou com curinga no nome ou no caminho relativo
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel_str, pattern):
                return True
            if fnmatch.fnmatch(rel_str, f"*/{pattern}") or fnmatch.fnmatch(rel_str, f"{pattern}/*"):
                return True

        return False


# ---------------------------------------------------------------------------
# SlashCommandCompleter
# ---------------------------------------------------------------------------


class SlashCommandCompleter(Completer):
    """Autocompletador para comandos slash (/), com busca difusa e metadados."""

    def __init__(
        self,
        commands: list[SlashCommandInfo] | None = None,
        dynamic: Callable[[], list[SlashCommandInfo]] | None = None,
    ) -> None:
        self._static = commands if commands is not None else list(OFFICIAL_SLASH_COMMANDS)
        self._dynamic = dynamic

    @property
    def commands(self) -> list[SlashCommandInfo]:
        """Comandos oficiais mais os dinâmicos (custom, plugins, prompts MCP)."""
        if self._dynamic is None:
            return self._static
        known = {c.name for c in self._static}
        return [*self._static, *(c for c in self._dynamic() if c.name not in known)]

    def _fuzzy_match(self, query: str, target: str) -> bool:
        """Verifica se todos os caracteres da query aparecem na ordem dentro de target."""
        it = iter(target.lower())
        return all(c in it for c in query.lower())

    def get_completions(
        self,
        document: Document,
        complete_event: CompleteEvent | None = None,
    ) -> Iterable[Completion]:
        text = document.text_before_cursor
        word = document.get_word_before_cursor(WORD=True)

        if not word.startswith("/"):
            # Se a linha toda começou com '/' e temos espaço, não autocompletamos comandos
            if text.strip().startswith("/") and "/" not in word:
                return
            if not word.startswith("/"):
                return

        query = word.lower()

        exact_prefix: list[tuple[SlashCommandInfo, int]] = []
        fuzzy_matches: list[tuple[SlashCommandInfo, int]] = []

        for cmd in self.commands:
            cmd_lower = cmd.name.lower()
            if cmd_lower.startswith(query):
                exact_prefix.append((cmd, len(cmd_lower)))
            elif query.startswith("/") and len(query) > 1 and self._fuzzy_match(query[1:], cmd_lower[1:]):
                fuzzy_matches.append((cmd, len(cmd_lower)))

        exact_prefix.sort(key=lambda x: x[1])
        fuzzy_matches.sort(key=lambda x: x[1])

        for cmd, _ in exact_prefix + fuzzy_matches:
            display_text = f"{cmd.icon} {cmd.name}" if cmd.icon else cmd.name
            yield Completion(
                text=cmd.name,
                start_position=-len(word),
                display=display_text,
                display_meta=cmd.description,
            )


# ---------------------------------------------------------------------------
# PathMentionCompleter
# ---------------------------------------------------------------------------


class PathMentionCompleter(Completer):
    """Autocompletador para menções de arquivos (@), respeitando .gitignore."""

    def __init__(self, workspace_root: Path | str | None = None) -> None:
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd()
        self.matcher = GitIgnoreMatcher(self.workspace_root)
        self._dir_cache: dict[str, tuple[float, list[tuple[str, bool]]]] = {}
        self._cache_ttl = 2.0  # segundos

    def _scan_dir(self, dir_path: Path) -> list[tuple[str, bool]]:
        """Lê diretório local com cache de curta duração para máxima responsividade."""
        cache_key = str(dir_path.resolve())
        now = time.time()
        if cache_key in self._dir_cache:
            ts, items = self._dir_cache[cache_key]
            if now - ts < self._cache_ttl:
                return items

        results: list[tuple[str, bool]] = []
        try:
            with os.scandir(dir_path) as it:
                for entry in it:
                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                    except OSError:
                        continue

                    if self.matcher.is_ignored(entry.name, is_dir=is_dir):
                        continue

                    results.append((entry.name, is_dir))
        except OSError:
            pass

        results.sort(key=lambda x: (not x[1], x[0].lower()))
        self._dir_cache[cache_key] = (now, results)
        return results

    def get_completions(
        self,
        document: Document,
        complete_event: CompleteEvent | None = None,
    ) -> Iterable[Completion]:
        word = document.get_word_before_cursor(WORD=True)
        if "@" not in word:
            return

        at_idx = word.rfind("@")
        query = word[at_idx + 1 :]
        start_pos = -len(query)

        # Se houver caminho com barra (ex: @src/ ou @docs/planning/)
        if "/" in query:
            parts = query.split("/")
            sub_dir_rel = "/".join(parts[:-1])
            file_prefix = parts[-1].lower()
            target_dir = self.workspace_root / sub_dir_rel

            if not target_dir.is_dir():
                return

            items = self._scan_dir(target_dir)
            for name, is_dir in items:
                if name.lower().startswith(file_prefix):
                    full_rel = f"{sub_dir_rel}/{name}" + ("/" if is_dir else "")
                    yield Completion(
                        text=full_rel,
                        start_position=start_pos,
                        display=f"{'● ' if is_dir else '› '}{name}{'/' if is_dir else ''}",
                        display_meta="dir" if is_dir else "file",
                    )
        else:
            # Query raiz (ex: @ ou @s ou @README)
            prefix = query.lower()
            items = self._scan_dir(self.workspace_root)
            for name, is_dir in items:
                if name.lower().startswith(prefix):
                    full_rel = name + ("/" if is_dir else "")
                    yield Completion(
                        text=full_rel,
                        start_position=start_pos,
                        display=f"{'● ' if is_dir else '› '}{name}{'/' if is_dir else ''}",
                        display_meta="dir" if is_dir else "file",
                    )


# ---------------------------------------------------------------------------
# OrionCompleter (Unified Completer)
# ---------------------------------------------------------------------------


class OrionCompleter(Completer):
    """Completador unificado do O.R.I.O.N com alternância de contexto (/ e @)."""

    def __init__(
        self,
        workspace_root: Path | str | None = None,
        commands: list[SlashCommandInfo] | None = None,
        dynamic_commands: Callable[[], list[SlashCommandInfo]] | None = None,
        mcp_resources: Callable[[], list[tuple[str, str]]] | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd()
        self._mcp_resources = mcp_resources
        self.slash_completer = SlashCommandCompleter(commands=commands, dynamic=dynamic_commands)
        self.path_completer = PathMentionCompleter(workspace_root=self.workspace_root)

    def get_completions(
        self,
        document: Document,
        complete_event: CompleteEvent | None = None,
    ) -> Iterable[Completion]:
        """Retorna sugestões dinâmicas:

        - Se o texto sob o cursor começar com '/', retorna comandos com metadados.
        - Se o texto sob o cursor começar com '@', retorna arquivos do workspace.
        """
        word = document.get_word_before_cursor(WORD=True)

        if word.startswith("/"):
            yield from self.slash_completer.get_completions(document, complete_event)
        elif "@" in word:
            if self._mcp_resources is not None and ":" in word:
                yield from self._resource_completions(word)
            else:
                yield from self.path_completer.get_completions(document, complete_event)
                yield from self._resource_completions(word)

    def _resource_completions(self, word: str) -> Iterable[Completion]:
        """``@servidor:recurso`` (resources MCP conectados)."""
        if self._mcp_resources is None:
            return
        typed = word[word.index("@") + 1 :]
        try:
            choices = self._mcp_resources()
        except Exception:
            return
        for ref, name in choices:
            if ref.lower().startswith(typed.lower()):
                yield Completion(ref, start_position=-len(typed), display=f"@{ref}", display_meta=name or "MCP")


# ---------------------------------------------------------------------------
# Mentions Parser & Safe Resolver
# ---------------------------------------------------------------------------

_MENTION_PATTERN = re.compile(r"(?:^|[\s\(\[\{<\"'])@([a-zA-Z0-9_\-\./\\]+)")


def parse_mentions(text: str) -> list[str]:
    """Extrai todas as menções de caminhos iniciadas por @ em um texto.

    Remove pontuações finais comuns (vírgula, ponto, parêntese, etc.).
    """
    matches = _MENTION_PATTERN.findall(text)
    cleaned: list[str] = []
    for raw in matches:
        item = raw.rstrip(".,:;!?)\"']")
        if item:
            cleaned.append(item)
    return cleaned


def resolve_mentions(
    text: str,
    workspace_root: Path | str | None = None,
) -> dict[str, Path]:
    """Resolve com segurança as menções @ para caminhos reais existentes no workspace.

    Impede ataques de directory traversal (ex: @../../etc/passwd).
    Retorna mapeamento {mencao_original: Path_resolvido}.
    """
    root = (Path(workspace_root) if workspace_root else Path.cwd()).resolve()
    mentions = parse_mentions(text)
    resolved_map: dict[str, Path] = {}

    for mention in mentions:
        try:
            target_path = (root / mention).resolve()
            # Validação estrita de confinamento dentro do workspace
            if not target_path.is_relative_to(root):
                continue

            if target_path.exists():
                resolved_map[mention] = target_path
        except Exception:
            continue

    return resolved_map
