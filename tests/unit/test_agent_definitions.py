"""Definições de subagents: embutidos, frontmatter, precedência e confiança (TOFU)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from orion.agents.definitions import (
    BUILTIN_NAMES,
    READ_ONLY_TOOLS,
    load_agents,
    parse_agent_markdown,
    project_agents_digest,
    trust_project_agents,
)
from orion.settings.models import AgentsSettings
from orion.settings.trust import ProjectTrust

LIMITS = AgentsSettings().resolved()

AUDITOR = """---
schema_version: 1
name: auditor
description: Audita um diretório
tools: [read_file, glob, grep]
model_tier: fast
max_turns: 12
budget_usd: 0.05
---
Você audita o código solicitado.
"""

GREEDY = """---
name: greedy
description: Quer tudo
tools: [write_file, run_command, read_file]
model_tier: heavy
max_turns: 90
budget_usd: 50
timeout_s: 7000
skills: [deploy]
memory: read
model_profile: premium
---
Faça de tudo.
"""


def _write(root: Path, name: str, text: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{name}.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_builtin_catalog(tmp_path: Path) -> None:
    catalog = load_agents(tmp_path / "home", tmp_path / "ws", limits=LIMITS)
    assert set(catalog.names()) == BUILTIN_NAMES == {"explore", "plan", "general-purpose", "code-review"}
    explore = catalog.get("explore")
    assert explore is not None and explore.model_tier == "fast"
    assert explore.tools == list(READ_ONLY_TOOLS) and explore.read_only
    assert catalog.get("general-purpose").tools is None  # type: ignore[union-attr]
    assert catalog.get("code-review").read_only  # type: ignore[union-attr]
    assert not catalog.project_needs_trust


def test_parse_native_frontmatter() -> None:
    agent, warnings = parse_agent_markdown(AUDITOR, "user")
    assert (agent.name, agent.model_tier, agent.max_turns, agent.budget_usd) == ("auditor", "fast", 12, 0.05)
    assert agent.tools == ["read_file", "glob", "grep"]
    assert agent.prompt.startswith("Você audita")
    assert warnings == []


def test_parse_claude_format_maps_names_and_drops_privilege_fields() -> None:
    text = """---
name: reviewer
description: Reviews
tools: Read, Grep, Bash
disallowedTools: Write
model: opus
maxTurns: 7
permissionMode: bypassPermissions
color: red
funky: 1
---
Prompt.
"""
    agent, warnings = parse_agent_markdown(text, "project")
    assert agent.tools == ["read_file", "grep", "run_command"]
    assert agent.disallowed_tools == ["write_file"]
    assert agent.model_tier == "heavy" and agent.max_turns == 7
    joined = " | ".join(warnings)
    assert "permissionmode" in joined and "descartado" in joined  # privilégio só diminui
    assert "funky" in joined


def test_concrete_model_id_is_pinned_and_warned() -> None:
    text = "---\nname: pin\ndescription: d\nmodel: gpt-9000\n---\nbody\n"
    agent, warnings = parse_agent_markdown(text, "user")
    assert agent.pinned_model == "gpt-9000" and agent.model_tier == "balanced"
    assert any("allow_pinned_model" in w for w in warnings)


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("sem frontmatter", "frontmatter"),
        ("---\nname: Bad Name\ndescription: d\n---\nbody", "nome"),
        ("---\nname: ok\ndescription: d\n---\n", "vazio"),
        ("---\nname: ok\ndescription: d\nisolation: sandbox\n---\nbody", "isolation"),
        ("---\nname: ok\ndescription: d\nmemory: write\n---\nbody", "memory"),
    ],
)
def test_invalid_definitions_are_rejected(text: str, fragment: str) -> None:
    with pytest.raises(ValueError, match=fragment):
        parse_agent_markdown(text, "user")


def test_precedence_project_over_user_over_plugin_and_reserved_names(tmp_path: Path) -> None:
    home, ws = tmp_path / "home", tmp_path / "ws"
    template = "---\nname: {n}\ndescription: {d}\ntools: [read_file]\n---\nbody\n"
    _write(ws / ".orion" / "agents", "dup", template.format(n="dup", d="projeto"))
    _write(home / "agents", "dup", template.format(n="dup", d="user"))
    _write(home / "agents", "explore", template.format(n="explore", d="sequestro"))
    plugin_dir = tmp_path / "plug"
    _write(plugin_dir, "dup", template.format(n="dup", d="plugin"))
    _write(plugin_dir, "only-plugin", template.format(n="only-plugin", d="plugin"))
    plugin = SimpleNamespace(agents_dir=plugin_dir)
    catalog = load_agents(home, ws, limits=LIMITS, plugins=[plugin], trust=ProjectTrust(home))
    assert catalog.get("dup").description == "projeto"  # type: ignore[union-attr]
    assert catalog.get("only-plugin").source == "plugin"  # type: ignore[union-attr]
    assert catalog.get("explore").source == "builtin"  # type: ignore[union-attr]  # nome reservado
    assert any("reservado" in n for n in catalog.notices)


def test_claude_agents_directory_is_read(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    _write(ws / ".claude" / "agents", "cc", "---\nname: cc\ndescription: d\ntools: Read\n---\nbody\n")
    catalog = load_agents(tmp_path / "home", ws, limits=LIMITS)
    assert catalog.get("cc") is not None and catalog.get("cc").tools == ["read_file"]  # type: ignore[union-attr]


def test_untrusted_project_agent_can_only_restrict(tmp_path: Path) -> None:
    home, ws = tmp_path / "home", tmp_path / "ws"
    _write(ws / ".orion" / "agents", "greedy", GREEDY)
    catalog = load_agents(home, ws, limits=LIMITS, trust=ProjectTrust(home))
    greedy = catalog.get("greedy")
    assert greedy is not None and catalog.project_needs_trust and not greedy.trusted
    assert greedy.tools == ["read_file"]  # só leitura: write_file e run_command caem
    assert greedy.model_tier == "balanced"  # heavy -> balanced
    assert greedy.model_profile is None and greedy.pinned_model is None
    assert greedy.budget_usd == LIMITS.default_budget_usd  # 50 -> teto padrão
    assert greedy.max_turns <= LIMITS.default_max_turns
    assert greedy.timeout_s == LIMITS.default_timeout_s
    assert greedy.skills == [] and greedy.memory == "none"


def test_untrusted_project_agent_without_tools_gets_read_only(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    _write(ws / ".orion" / "agents", "inherits", "---\nname: inherits\ndescription: d\n---\nbody\n")
    catalog = load_agents(tmp_path / "home", ws, limits=LIMITS)
    assert catalog.get("inherits").tools == list(READ_ONLY_TOOLS)  # type: ignore[union-attr]


def test_trust_unlocks_agents_and_any_change_revokes_it(tmp_path: Path) -> None:
    home, ws = tmp_path / "home", tmp_path / "ws"
    path = _write(ws / ".orion" / "agents", "greedy", GREEDY)
    trust = ProjectTrust(home)
    catalog = load_agents(home, ws, limits=LIMITS, trust=trust)
    assert trust_project_agents(catalog, trust)

    trusted = load_agents(home, ws, limits=LIMITS, trust=trust)
    greedy = trusted.get("greedy")
    assert greedy is not None and greedy.trusted and not trusted.project_needs_trust
    assert greedy.tools == ["write_file", "run_command", "read_file"]
    assert greedy.model_tier == "heavy"

    path.write_text(GREEDY + "\nextra\n", encoding="utf-8")  # qualquer mudança invalida
    again = load_agents(home, ws, limits=LIMITS, trust=trust)
    assert again.project_needs_trust and not again.get("greedy").trusted  # type: ignore[union-attr]


def test_digest_none_without_project_agents_and_trust_noop(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    assert project_agents_digest(ws) is None
    catalog = load_agents(tmp_path / "home", ws, limits=LIMITS)
    assert trust_project_agents(catalog, ProjectTrust(tmp_path / "home")) is False


def test_broken_file_is_reported_not_fatal(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write(home / "agents", "broken", "---\n: : :\n---\nbody")
    _write(home / "agents", "fine", AUDITOR.replace("auditor", "fine"))
    catalog = load_agents(home, tmp_path / "ws", limits=LIMITS)
    assert catalog.get("fine") is not None and catalog.get("broken") is None
    assert any("broken" in n for n in catalog.notices)
