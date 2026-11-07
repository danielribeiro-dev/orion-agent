"""
O.R.I.O.N — Decision Log (v0.5.0 Sprint 3)

Tool ``record_decision``: registra uma decisão de engenharia tomada com o Senhor em duas
superfícies — um fato CONFIRMED no ``FactsStore`` (recall futuro; o anti-poisoning impede
que inferências o sobrescrevam) e um arquivo legível em ``.orion/decisions/NNNN-slug.md``
no workspace (revisável e versionável pelo usuário).

Nível PEP 3: grava um fato CONFIRMED, que só o usuário deveria poder declarar; a
confirmação explícita é o que dá lastro a essa promoção.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from orion.memory.facts_store import FactsStore
from orion.memory.models import FactCategory, FactEntry, FactStatus
from orion.runtime.provider import RuntimeResult

_FILE_RE = re.compile(r"^(\d{4})-")
_FACT_VALUE_MAX = 600


def slugify(text: str, limit: int = 48) -> str:
    """ASCII kebab-case estável para nomes de arquivo e chaves."""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")
    return slug[:limit].strip("-") or "decisao"


class RecordDecisionTool:
    """Registra uma decisão (título, decisão, motivo, alternativas)."""

    TOOL_NAME = "record_decision"
    name = TOOL_NAME
    description = (
        "Record an engineering decision agreed with the user (title, decision, rationale, "
        "alternatives considered). Use after a decision is explicitly made, never for guesses."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short decision title."},
            "decision": {"type": "string", "description": "What was decided."},
            "rationale": {"type": "string", "description": "Why it was decided."},
            "alternatives": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Options considered and rejected.",
            },
        },
        "required": ["title", "decision", "rationale"],
    }

    def __init__(self, facts_store: FactsStore, decisions_dir: Path) -> None:
        self._store = facts_store
        self._dir = decisions_dir

    def supports(self, name: str) -> bool:
        return name == self.TOOL_NAME

    def _next_number(self) -> int:
        highest = 0
        if self._dir.is_dir():
            for entry in self._dir.iterdir():
                match = _FILE_RE.match(entry.name)
                if match:
                    highest = max(highest, int(match.group(1)))
        return highest + 1

    def execute(self, params: dict[str, Any]) -> RuntimeResult:
        title = str(params.get("title", "")).strip()
        decision = str(params.get("decision", "")).strip()
        rationale = str(params.get("rationale", "")).strip()
        alternatives = [str(a).strip() for a in params.get("alternatives") or [] if str(a).strip()]
        if not (title and decision and rationale):
            return RuntimeResult.fail("'title', 'decision' e 'rationale' são obrigatórios.")

        slug = slugify(title)
        number = self._next_number()
        path = self._dir / f"{number:04d}-{slug}.md"
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        body = [
            f"# {number:04d} — {title}",
            "",
            f"> Data: {today} · Status: CONFIRMED",
            "",
            "## Decisão",
            decision,
            "",
            "## Motivo",
            rationale,
        ]
        if alternatives:
            body += ["", "## Alternativas descartadas", *[f"- {a}" for a in alternatives]]
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(body) + "\n", encoding="utf-8")
        except OSError as exc:
            return RuntimeResult.fail(f"Não foi possível gravar {path}: {exc}")

        value = f"{decision} (motivo: {rationale})"[:_FACT_VALUE_MAX]
        fact = self._store.upsert(
            FactEntry(
                key=f"decision_{slug}",
                value=value,
                category=FactCategory.PROJECT_ARCHITECTURE,
                status=FactStatus.CONFIRMED,
                confidence=1.0,
                source="decision",
            )
        )
        return RuntimeResult.ok(
            f"Decisão {number:04d} registrada: {path.name} (fato '{fact.key}' CONFIRMED).",
            fact_key=fact.key,
            path=str(path),
            number=number,
        )
