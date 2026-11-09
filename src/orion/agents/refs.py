"""Resultados de subagents por referência (``ref://agents/<id>/result.md``).

O texto completo do filho vai para ``~/.orion/agents/<id>/`` e só um resumo curto volta ao
pai. A referência sobrevive à compactação do contexto do pai: basta lê-la com ``read_file``.
"""

from __future__ import annotations

import re
from pathlib import Path

REF_PREFIX = "ref://agents/"
_ID = re.compile(r"^agent_[0-9a-f]{6,32}$")
_FILES = frozenset({"result.md", "transcript.jsonl", "meta.json"})


def agents_dir(home: Path) -> Path:
    return home / "agents"


def agent_dir(home: Path, agent_id: str) -> Path:
    return agents_dir(home) / agent_id


def make_ref(agent_id: str, name: str = "result.md") -> str:
    return f"{REF_PREFIX}{agent_id}/{name}"


def resolve_ref(ref: str, home: Path) -> Path | None:
    """Caminho do arquivo de uma ``ref://agents/...``; ``None`` se inválida (sem traversal)."""
    if not ref.startswith(REF_PREFIX):
        return None
    parts = ref[len(REF_PREFIX) :].split("/")
    if len(parts) != 2:
        return None
    agent_id, name = parts
    if not _ID.match(agent_id) or name not in _FILES:
        return None
    return agent_dir(home, agent_id) / name
