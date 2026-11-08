"""Settings em camadas, confiança de projeto e persistência privada."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from orion.settings import (
    ProjectTrust,
    Settings,
    append_local_rule,
    load_settings,
    local_settings_path,
    merge,
    project_settings_path,
    save_user_settings,
    user_settings_path,
    write_private_json,
)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    return path


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    path = tmp_path / "ws"
    (path / ".orion").mkdir(parents=True)
    return path


def _put(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


class TestPrecedence:
    def test_escalares_local_vence_projeto_vence_user(self, home: Path, ws: Path) -> None:
        _put(user_settings_path(home), {"model": "u", "effort": "low"})
        _put(project_settings_path(ws), {"model": "p", "effort": "high"})
        _put(local_settings_path(ws), {"model": "l"})
        eff = load_settings(home, ws).effective
        assert eff.model == "l"
        assert eff.effort == "high"

    def test_listas_concatenam_sem_duplicar(self) -> None:
        a = Settings.model_validate({"permissions": {"deny": ["x", "y"]}})
        b = Settings.model_validate({"permissions": {"deny": ["y", "z"]}})
        assert merge([a, b]).permissions.deny == ["x", "y", "z"]

    def test_hooks_de_camadas_concatenam(self) -> None:
        a = Settings.model_validate({"hooks": {"Stop": [{"command": "a"}]}})
        b = Settings.model_validate({"hooks": {"Stop": [{"command": "b"}]}})
        merged = merge([a, b]).hooks["Stop"]
        assert [h.command for h in merged] == ["a", "b"]

    def test_chaves_desconhecidas_sao_ignoradas(self, home: Path) -> None:
        _put(user_settings_path(home), {"model": "m", "coisa_nova": 1})
        assert load_settings(home).effective.model == "m"

    def test_arquivo_invalido_vira_aviso(self, home: Path) -> None:
        _put(user_settings_path(home), {"daily_budget_usd": "muito"})
        loaded = load_settings(home)
        assert loaded.effective == Settings()
        assert loaded.notices

    def test_json_quebrado_e_ignorado(self, home: Path) -> None:
        user_settings_path(home).write_text("{nao e json", encoding="utf-8")
        assert load_settings(home).effective == Settings()


class TestLegacyMigration:
    def test_le_config_json_quando_nao_ha_settings(self, home: Path) -> None:
        _put(home / "config.json", {"model": "legado", "mode": "plan", "extra": 1})
        eff = load_settings(home).effective
        assert (eff.model, eff.mode) == ("legado", "plan")

    def test_settings_json_tem_prioridade_sobre_legado(self, home: Path) -> None:
        _put(home / "config.json", {"model": "legado"})
        _put(user_settings_path(home), {"model": "novo"})
        assert load_settings(home).effective.model == "novo"

    def test_save_migra_legado_sem_apagar_config(self, home: Path) -> None:
        _put(home / "config.json", {"model": "legado", "effort": "low"})
        save_user_settings(home, {"model": "novo"})
        data = json.loads(user_settings_path(home).read_text(encoding="utf-8"))
        assert data == {"model": "novo", "effort": "low"}
        assert (home / "config.json").exists()


class TestProjectTrust:
    def test_projeto_sem_risco_vale_sem_confianca(self, home: Path, ws: Path) -> None:
        _put(project_settings_path(ws), {"model": "p", "permissions": {"deny": ["x"]}})
        loaded = load_settings(home, ws)
        assert not loaded.project_needs_trust
        assert loaded.effective.model == "p"

    def test_projeto_de_risco_sem_confianca_so_restringe(self, home: Path, ws: Path) -> None:
        _put(
            project_settings_path(ws),
            {
                "model": "p",
                "mode": "auto",
                "permissions": {"allow": ["run_command"], "deny": ["rm"], "ask": ["git push"]},
                "hooks": {"PreToolUse": [{"command": "evil.sh"}]},
                "env": {"X": "1"},
                "mcp": {"srv": {"command": "uvx"}},
                "daily_budget_usd": 999,
            },
        )
        loaded = load_settings(home, ws)
        eff = loaded.effective
        assert loaded.project_needs_trust
        assert eff.model == "p"
        assert eff.mode is None
        assert eff.permissions.allow == []
        assert eff.permissions.deny == ["rm"]
        assert eff.permissions.ask == ["git push"]
        assert eff.hooks == {} and eff.env == {} and eff.mcp == {}
        assert eff.daily_budget_usd is None

    def test_confianca_libera_o_conteudo(self, home: Path, ws: Path) -> None:
        _put(project_settings_path(ws), {"hooks": {"Stop": [{"command": "ok.sh"}]}})
        first = load_settings(home, ws)
        assert first.project_digest
        ProjectTrust(home).trust(ws, first.project_digest)
        second = load_settings(home, ws)
        assert not second.project_needs_trust
        assert second.effective.hooks["Stop"][0].command == "ok.sh"

    def test_mudanca_no_arquivo_exige_confianca_de_novo(self, home: Path, ws: Path) -> None:
        path = project_settings_path(ws)
        _put(path, {"hooks": {"Stop": [{"command": "ok.sh"}]}})
        digest = load_settings(home, ws).project_digest
        assert digest
        ProjectTrust(home).trust(ws, digest)
        _put(path, {"hooks": {"Stop": [{"command": "outro.sh"}]}})
        again = load_settings(home, ws)
        assert again.project_needs_trust
        assert again.effective.hooks == {}

    def test_camada_local_e_sempre_confiavel(self, home: Path, ws: Path) -> None:
        _put(local_settings_path(ws), {"permissions": {"allow": ["git status:*"]}})
        assert load_settings(home, ws).effective.permissions.allow == ["git status:*"]

    def test_resumo_lista_o_que_o_projeto_pede(self, home: Path, ws: Path) -> None:
        _put(
            project_settings_path(ws),
            {"hooks": {"Stop": [{"command": "a.sh"}]}, "permissions": {"allow": ["git status"]}},
        )
        text = "\n".join(load_settings(home, ws).project_summary())
        assert "hook Stop: a.sh" in text and "allow: git status" in text

    def test_trust_persiste_com_0600(self, home: Path, ws: Path) -> None:
        ProjectTrust(home).trust(ws, "abc")
        assert _mode(home / "trusted_projects.json") == 0o600
        assert ProjectTrust(home).is_trusted(ws, "abc")
        ProjectTrust(home).revoke(ws)
        assert not ProjectTrust(home).is_trusted(ws, "abc")


class TestPrivateWrites:
    def test_write_private_json_usa_0600_e_e_atomico(self, tmp_path: Path) -> None:
        target = tmp_path / "novo" / "a.json"
        write_private_json(target, {"k": 1})
        assert _mode(target) == 0o600
        assert not target.with_name("a.json.tmp").exists()
        assert json.loads(target.read_text(encoding="utf-8")) == {"k": 1}

    def test_settings_local_fica_0600(self, ws: Path) -> None:
        append_local_rule(ws, "allow", "git status:*")
        assert _mode(local_settings_path(ws)) == 0o600

    def test_append_local_rule_nao_duplica(self, ws: Path) -> None:
        append_local_rule(ws, "allow", "git status:*")
        append_local_rule(ws, "allow", "git status:*")
        data = json.loads(local_settings_path(ws).read_text(encoding="utf-8"))
        assert data["permissions"]["allow"] == ["git status:*"]
