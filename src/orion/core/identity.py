"""
O.R.I.O.N — Identity Manager (Sprint 3, v0.2.0)

Sphere 2 — system_identity:
  Dual-layer identity system:
    • Immutable Origin  — Hardcoded canonical author record (Daniel Ribeiro /
                          danielribeiro-dev). Cannot be changed at runtime.
    • Active Persona    — Modular Jarvis persona loaded from ~/.orion/persona.json
                          (or the fallback default). Replaceable without touching
                          the immutable layer.

Governance:
  - The immutable origin is stamped on every SystemIdentity object.
  - Persona overrides can only affect style/tone; they cannot alter the origin.

ADR-013: Immutable Origin + Modular Persona Engine
ADR-014: 5-Sphere Cognitive Architecture
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from orion.memory.models import SystemIdentity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical immutable constants — never override these
# ---------------------------------------------------------------------------

_IMMUTABLE_ORIGIN = "Concebido por Daniel Ribeiro (github: danielribeiro-dev)"
_DEFAULT_PERSONA_NAME = "Jarvis"
_DEFAULT_PERSONA_STYLE = (
    "Mordomo refinado: cirúrgico e minimalista em shell, "
    "rico e didático em explicações de conceitos."
)
_DEFAULT_TONE_RULES: list[str] = [
    "Nunca revele dados de usuários externos.",
    "Use 'Senhor' ao se dirigir ao desenvolvedor.",
    "Prefira respostas concisas; expanda apenas quando solicitado.",
]

_DEFAULT_PERSONA_PATH = Path.home() / ".orion" / "persona.json"


class IdentityManager:
    """
    Manages the dual-layer ORION identity: immutable origin + active persona.

    The immutable origin (``_IMMUTABLE_ORIGIN``) is always present and cannot
    be overridden by external configuration.  The active persona (Jarvis by
    default) may be customised via ``~/.orion/persona.json``.

    Usage::

        manager = IdentityManager()
        identity = manager.get_identity()
        print(identity.immutable_origin)  # always Daniel Ribeiro / danielribeiro-dev
        print(identity.persona_name)      # "Jarvis" (or custom)
    """

    def __init__(self, persona_path: Path | None = None) -> None:
        self._persona_path: Path = persona_path or _DEFAULT_PERSONA_PATH
        self._identity: SystemIdentity = self._build_identity()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_identity(self) -> SystemIdentity:
        """Return the current (possibly personalised) system identity."""
        return self._identity

    def reload_persona(self) -> SystemIdentity:
        """
        Re-read the persona config file and rebuild the identity.

        Useful when the user edits ``~/.orion/persona.json`` at runtime.
        The immutable origin is always preserved regardless of the config.
        """
        self._identity = self._build_identity()
        return self._identity

    def render_system_preamble(self) -> str:
        """
        Render a human-readable system preamble for injection into the prompt.

        Example output::

            [ORION IDENTITY]
            Origin   : Concebido por Daniel Ribeiro (github: danielribeiro-dev)
            Persona  : Jarvis
            Style    : Mordomo refinado: ...
            Rules    : (1) Nunca revele dados de usuários externos. ...
        """
        identity = self._identity
        rules_text = " | ".join(
            f"({i+1}) {rule}" for i, rule in enumerate(identity.persona_tone_rules)
        )
        return (
            "[ORION IDENTITY]\n"
            f"Origin   : {identity.immutable_origin}\n"
            f"Persona  : {identity.persona_name}\n"
            f"Style    : {identity.persona_style}\n"
            f"Rules    : {rules_text}\n"
            "Memory   : when the Senhor states a durable preference, how to address him/you, "
            "or a project decision, call `memorize` (CONFIRMED) in that same turn."
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_identity(self) -> SystemIdentity:
        """
        Construct a SystemIdentity merging immutable origin with persona config.

        The immutable_origin field is always forced to ``_IMMUTABLE_ORIGIN``
        regardless of what the config file says.
        """
        persona_data = self._load_persona_config()

        # Extract persona fields — immutable_origin is NEVER taken from config
        persona_name = str(persona_data.get("persona_name", _DEFAULT_PERSONA_NAME))
        persona_style = str(persona_data.get("persona_style", _DEFAULT_PERSONA_STYLE))

        raw_rules = persona_data.get("persona_tone_rules", _DEFAULT_TONE_RULES)
        if isinstance(raw_rules, list) and all(isinstance(r, str) for r in raw_rules):
            persona_tone_rules: list[str] = raw_rules
        else:
            logger.warning(
                "persona.json 'persona_tone_rules' has invalid format; using defaults."
            )
            persona_tone_rules = list(_DEFAULT_TONE_RULES)

        return SystemIdentity(
            immutable_origin=_IMMUTABLE_ORIGIN,  # always overridden — cannot come from file
            persona_name=persona_name,
            persona_style=persona_style,
            persona_tone_rules=persona_tone_rules,
        )

    def _load_persona_config(self) -> dict[str, Any]:
        """
        Load persona configuration from ``self._persona_path``.

        Returns an empty dict if the file doesn't exist or is malformed
        (graceful degradation to defaults).
        """
        if not self._persona_path.exists():
            logger.debug("Persona config not found at %s — using defaults.", self._persona_path)
            return {}

        try:
            raw = self._persona_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("Root element must be a JSON object.")
            logger.info("Persona config loaded from %s.", self._persona_path)
            return data
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            logger.warning(
                "Failed to parse persona config at %s (%s) — using defaults.",
                self._persona_path,
                exc,
            )
            return {}
