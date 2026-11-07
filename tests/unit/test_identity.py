"""
Tests — IdentityManager (Sprint 3, v0.2.0)

Validates:
  - Immutable origin is always Daniel Ribeiro / danielribeiro-dev (TEST 4)
  - Default persona (Jarvis) is loaded when no persona.json exists
  - Custom persona.json is loaded and merged (immutable origin preserved)
  - Persona file with invalid format falls back gracefully to defaults
  - render_system_preamble() format is correct
"""

from __future__ import annotations

import json

from orion.core.identity import _IMMUTABLE_ORIGIN, IdentityManager
from orion.memory.models import SystemIdentity


class TestImmutableOrigin:
    """TEST 4 (spec): Persona 'Jarvis' + tratamento 'Senhor' carregados
    sem apagar a autoria imutável de Daniel (danielribeiro-dev)."""

    def test_immutable_origin_always_present(self, tmp_path):
        """The immutable origin is always Daniel Ribeiro, regardless of config."""
        manager = IdentityManager(persona_path=tmp_path / "no_persona.json")
        identity = manager.get_identity()

        assert "Daniel Ribeiro" in identity.immutable_origin
        assert "danielribeiro-dev" in identity.immutable_origin

    def test_immutable_origin_exact_value(self, tmp_path):
        manager = IdentityManager(persona_path=tmp_path / "nonexistent.json")
        identity = manager.get_identity()

        assert identity.immutable_origin == _IMMUTABLE_ORIGIN

    def test_immutable_origin_survives_persona_override(self, tmp_path):
        """Even if persona.json tries to set immutable_origin, it is ignored."""
        persona_file = tmp_path / "persona.json"
        persona_file.write_text(
            json.dumps({
                "immutable_origin": "Hacked by Eve",
                "persona_name": "Evil Bot",
                "persona_style": "Deceptive",
            })
        )
        manager = IdentityManager(persona_path=persona_file)
        identity = manager.get_identity()

        assert identity.immutable_origin == _IMMUTABLE_ORIGIN
        assert "Hacked" not in identity.immutable_origin


class TestDefaultPersona:
    def test_default_persona_name_is_jarvis(self, tmp_path):
        manager = IdentityManager(persona_path=tmp_path / "missing.json")
        identity = manager.get_identity()
        assert identity.persona_name == "Jarvis"

    def test_default_tone_rules_present(self, tmp_path):
        manager = IdentityManager(persona_path=tmp_path / "missing.json")
        identity = manager.get_identity()
        assert len(identity.persona_tone_rules) > 0
        # Default rules mention 'Senhor'
        combined = " ".join(identity.persona_tone_rules)
        assert "Senhor" in combined

    def test_returns_system_identity_model(self, tmp_path):
        manager = IdentityManager(persona_path=tmp_path / "missing.json")
        identity = manager.get_identity()
        assert isinstance(identity, SystemIdentity)


class TestCustomPersona:
    def test_custom_persona_name_loaded(self, tmp_path):
        persona_file = tmp_path / "persona.json"
        persona_file.write_text(
            json.dumps({
                "persona_name": "Alfred",
                "persona_style": "Butlerian, precise.",
            })
        )
        manager = IdentityManager(persona_path=persona_file)
        identity = manager.get_identity()

        assert identity.persona_name == "Alfred"
        assert identity.persona_style == "Butlerian, precise."
        # Immutable origin still intact
        assert identity.immutable_origin == _IMMUTABLE_ORIGIN

    def test_custom_tone_rules_loaded(self, tmp_path):
        custom_rules = ["Rule 1: Always be brief.", "Rule 2: Cite sources."]
        persona_file = tmp_path / "persona.json"
        persona_file.write_text(
            json.dumps({
                "persona_name": "CustomBot",
                "persona_tone_rules": custom_rules,
            })
        )
        manager = IdentityManager(persona_path=persona_file)
        identity = manager.get_identity()

        assert identity.persona_tone_rules == custom_rules

    def test_partial_config_uses_defaults_for_missing_keys(self, tmp_path):
        """Only persona_name provided → style and rules fall back to defaults."""
        persona_file = tmp_path / "persona.json"
        persona_file.write_text(json.dumps({"persona_name": "R2D2"}))

        manager = IdentityManager(persona_path=persona_file)
        identity = manager.get_identity()

        assert identity.persona_name == "R2D2"
        # Style should use default
        assert len(identity.persona_style) > 0
        # Default tone rules should apply
        assert len(identity.persona_tone_rules) > 0


class TestPersonaFallback:
    def test_malformed_json_uses_defaults(self, tmp_path):
        persona_file = tmp_path / "persona.json"
        persona_file.write_text("{invalid json!!!")

        manager = IdentityManager(persona_path=persona_file)
        identity = manager.get_identity()

        # Falls back to Jarvis defaults
        assert identity.persona_name == "Jarvis"
        assert identity.immutable_origin == _IMMUTABLE_ORIGIN

    def test_non_dict_json_uses_defaults(self, tmp_path):
        persona_file = tmp_path / "persona.json"
        persona_file.write_text('["not", "an", "object"]')

        manager = IdentityManager(persona_path=persona_file)
        identity = manager.get_identity()

        assert identity.persona_name == "Jarvis"

    def test_invalid_tone_rules_type_uses_defaults(self, tmp_path):
        """If persona_tone_rules is not a list of strings, default rules are used."""
        persona_file = tmp_path / "persona.json"
        persona_file.write_text(
            json.dumps({
                "persona_name": "TestBot",
                "persona_tone_rules": "should be a list, not a string",
            })
        )
        manager = IdentityManager(persona_path=persona_file)
        identity = manager.get_identity()

        # Should fall back to default tone rules
        assert isinstance(identity.persona_tone_rules, list)


class TestReloadPersona:
    def test_reload_picks_up_new_file(self, tmp_path):
        persona_file = tmp_path / "persona.json"
        manager = IdentityManager(persona_path=persona_file)

        # Initially no file — defaults
        assert manager.get_identity().persona_name == "Jarvis"

        # Write a new persona
        persona_file.write_text(json.dumps({"persona_name": "ORACLE"}))
        manager.reload_persona()

        assert manager.get_identity().persona_name == "ORACLE"
        assert manager.get_identity().immutable_origin == _IMMUTABLE_ORIGIN


class TestRenderPreamble:
    def test_preamble_contains_origin(self, tmp_path):
        manager = IdentityManager(persona_path=tmp_path / "none.json")
        preamble = manager.render_system_preamble()

        assert "Daniel Ribeiro" in preamble
        assert "danielribeiro-dev" in preamble

    def test_preamble_contains_persona(self, tmp_path):
        manager = IdentityManager(persona_path=tmp_path / "none.json")
        preamble = manager.render_system_preamble()

        assert "Jarvis" in preamble

    def test_preamble_is_non_empty_string(self, tmp_path):
        manager = IdentityManager(persona_path=tmp_path / "none.json")
        preamble = manager.render_system_preamble()
        assert isinstance(preamble, str)
        assert len(preamble) > 50
