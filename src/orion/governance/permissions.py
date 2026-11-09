"""
O.R.I.O.N — Governance Permissions
Defines ActionLevel risk tiers and WorkspaceScope path guards.

Reference: docs/architecture/GOVERNANCE_PEP.md
"""

from __future__ import annotations

from enum import IntEnum
from pathlib import Path

from orion.core.events import RiskLevel


class ActionLevel(IntEnum):
    """Static risk classification for every registered tool.

    LEVEL_0  — Informative / in-memory: no side-effects.
               Executes immediately without logging.
    LEVEL_1  — Passive read: read_file, search_files, status queries.
               Executes with audit log entry.
    LEVEL_2  — Project mutation: write_file, edit_file inside workspace.
               Requires explicit [Y/n] confirmation in Supervised Mode.
    LEVEL_3  — Critical system: run_command (arbitrary shell), file deletion,
               network changes.
               Requires explicit confirmation with full command display.
    """

    LEVEL_0 = 0
    LEVEL_1 = 1
    LEVEL_2 = 2
    LEVEL_3 = 3


# Static mapping: tool name → default ActionLevel
TOOL_LEVELS: dict[str, ActionLevel] = {
    "read_file": ActionLevel.LEVEL_1,
    "search_files": ActionLevel.LEVEL_1,
    "write_file": ActionLevel.LEVEL_2,
    "edit_file": ActionLevel.LEVEL_2,
    "run_command": ActionLevel.LEVEL_3,
    # Cognitive & skills tools (v0.2.0)
    "inspect_environment": ActionLevel.LEVEL_1,
    "recall": ActionLevel.LEVEL_1,
    "use_skill": ActionLevel.LEVEL_1,
    "memorize": ActionLevel.LEVEL_2,
    "deprecate_fact": ActionLevel.LEVEL_2,
    # Grava fato CONFIRMED (só o usuário deveria promover): sempre confirmado (v0.5.0 Sprint 3).
    "record_decision": ActionLevel.LEVEL_3,
    # Paridade de ferramentas (v0.5.0 Sprint 4)
    "glob": ActionLevel.LEVEL_1,
    "grep": ActionLevel.LEVEL_1,
    "bash_output": ActionLevel.LEVEL_1,
    "kill_shell": ActionLevel.LEVEL_2,
    "notebook_edit": ActionLevel.LEVEL_2,
    "web_fetch": ActionLevel.LEVEL_2,
    "web_search": ActionLevel.LEVEL_2,
    # Estado de sessão / interação: sem efeito no sistema; a saída do plan mode exige modal.
    "todo_write": ActionLevel.LEVEL_0,
    "ask_user": ActionLevel.LEVEL_0,
    "enter_plan_mode": ActionLevel.LEVEL_0,
    "exit_plan_mode": ActionLevel.LEVEL_0,
    # Subagents (v0.5.0 Sprint 6): delegar não muda nada por si só. O filho roda com PEP próprio
    # sob o teto do pai (ADR-028), então o risco real é decidido a cada tool que ele chamar.
    "task": ActionLevel.LEVEL_1,
    # Tasks em segundo plano (Sprint 6B): disparar/consultar não amplia privilégio (mesmo teto do
    # pai); cancelar interfere no trabalho em andamento, então pede o mesmo que `kill_shell`.
    "task_create": ActionLevel.LEVEL_1,
    "task_list": ActionLevel.LEVEL_0,
    "task_get": ActionLevel.LEVEL_1,
    "task_stop": ActionLevel.LEVEL_2,
    "send_message": ActionLevel.LEVEL_1,
    # Daemon, agenda e presença (Sprint 7, ADR-032/036): ligar o daemon, agendar trabalho sem
    # humano e mudar como o ORION alcança o Senhor sempre pedem confirmação (fora de FULLY_AUTO).
    "daemon_control": ActionLevel.LEVEL_3,
    "schedule_create": ActionLevel.LEVEL_3,
    "schedule_delete": ActionLevel.LEVEL_3,
    "schedule_list": ActionLevel.LEVEL_0,
    "presence_rule_create": ActionLevel.LEVEL_3,
    "presence_rule_delete": ActionLevel.LEVEL_3,
    "presence_rule_list": ActionLevel.LEVEL_0,
}

#: Tools que abrem modal no terminal: nunca rodam em paralelo com outras.
SERIAL_TOOLS: frozenset[str] = frozenset({"ask_user", "enter_plan_mode", "exit_plan_mode"})

# ActionLevel -> RiskLevel carried by Action events (single source of truth).
_RISK_BY_LEVEL: dict[ActionLevel, RiskLevel] = {
    ActionLevel.LEVEL_0: RiskLevel.SAFE,
    ActionLevel.LEVEL_1: RiskLevel.SAFE,
    ActionLevel.LEVEL_2: RiskLevel.CONTROLLED,
    ActionLevel.LEVEL_3: RiskLevel.CRITICAL,
}
_LEVEL_BY_RISK: dict[RiskLevel, ActionLevel] = {
    RiskLevel.SAFE: ActionLevel.LEVEL_1,
    RiskLevel.CONTROLLED: ActionLevel.LEVEL_2,
    RiskLevel.ELEVATED: ActionLevel.LEVEL_3,
    RiskLevel.CRITICAL: ActionLevel.LEVEL_3,
}


# Runtime-registered levels (e.g. MCP tools discovered after connect).
# Kept separate from the static map so it can be cleared on disconnect.
_DYNAMIC_LEVELS: dict[str, ActionLevel] = {}


def register_tool_level(tool_name: str, level: ActionLevel) -> None:
    """Register (or override) the ActionLevel of a dynamically discovered tool."""
    _DYNAMIC_LEVELS[tool_name] = level


def unregister_tool_levels(prefix: str) -> None:
    """Drop every dynamic level whose tool name starts with *prefix*."""
    for key in [k for k in _DYNAMIC_LEVELS if k.startswith(prefix)]:
        del _DYNAMIC_LEVELS[key]


def is_dynamic_mutating(tool_name: str) -> bool:
    """True if *tool_name* was dynamically registered as LEVEL_2 or higher."""
    level = _DYNAMIC_LEVELS.get(tool_name)
    return level is not None and level >= ActionLevel.LEVEL_2


def tool_action_level(tool_name: str) -> ActionLevel:
    """Return the ActionLevel for a given tool name.

    Static map first, then dynamic registrations. Unknown tools default to
    LEVEL_3 (safest assumption).
    """
    if tool_name in TOOL_LEVELS:
        return TOOL_LEVELS[tool_name]
    return _DYNAMIC_LEVELS.get(tool_name, ActionLevel.LEVEL_3)


def tool_risk_level(tool_name: str) -> RiskLevel:
    """RiskLevel of *tool_name*, derived from its ActionLevel (unknown => CRITICAL)."""
    return _RISK_BY_LEVEL[tool_action_level(tool_name)]


def risk_to_action_level(risk: RiskLevel) -> ActionLevel:
    """Map an explicit RiskLevel (tool registration hint) to an ActionLevel."""
    return _LEVEL_BY_RISK[risk]


def is_read_only_tool(tool_name: str) -> bool:
    """True if *tool_name* has no side effects (LEVEL_0/1) and may run in parallel."""
    return tool_name not in SERIAL_TOOLS and tool_action_level(tool_name) <= ActionLevel.LEVEL_1


class WorkspaceScope:
    """Restricts filesystem operations to a set of authorised root paths.

    Any path that resolves outside every authorised root is rejected.
    The check is canonical-path-based to prevent symlink traversal.
    """

    def __init__(self, roots: list[Path] | None = None) -> None:
        if roots is None:
            roots = [Path.cwd()]
        self._roots: list[Path] = [r.resolve() for r in roots]

    @classmethod
    def default(cls) -> WorkspaceScope:
        """Return a scope anchored at the current working directory."""
        return cls([Path.cwd()])

    def is_allowed(self, path: Path | str) -> bool:
        """Return True if *path* is inside at least one authorised root."""
        target = Path(path).expanduser().resolve()
        return any(self._is_inside(target, root) for root in self._roots)

    @staticmethod
    def _is_inside(target: Path, root: Path) -> bool:
        try:
            target.relative_to(root)
            return True
        except ValueError:
            return False

    def assert_allowed(self, path: Path | str) -> None:
        """Raise PermissionError if *path* is outside every authorised root."""
        if not self.is_allowed(path):
            raise PermissionError(
                f"Path '{path}' is outside the authorised workspace. "
                f"Allowed roots: {[str(r) for r in self._roots]}"
            )

    def add_root(self, path: Path | str) -> None:
        """Extend the scope with an additional authorised root."""
        self._roots.append(Path(path).resolve())

    @property
    def roots(self) -> list[Path]:
        return list(self._roots)

    def __repr__(self) -> str:  # pragma: no cover
        return f"WorkspaceScope(roots={[str(r) for r in self._roots]})"
