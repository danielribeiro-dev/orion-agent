"""Regressões da rodada manual de 09/11/2026 (R-03, R-08, R-10, R-11, R-12, R-13, R-14, R-04)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from orion.core.events import Action, RiskLevel
from orion.gateway.credentials import load_openrouter_key
from orion.gateway.errors import RateLimitError
from orion.gateway.models import ComplexityTier
from orion.gateway.providers.base import is_retryable
from orion.gateway.providers.openrouter import OpenRouterProvider
from orion.governance.audit import AuditLogger
from orion.governance.nuclear import BlastRadius, NuclearChallengeResult, NuclearSafetyGate
from orion.governance.pep import (
    ActionDenied,
    AutonomyMode,
    PolicyEnforcementPoint,
    is_protected_state_path,
)
from orion.governance.permissions import WorkspaceScope
from orion.memory.auto_recall import _is_noise
from orion.runtime.tools.edit_file import EditFileTool
from orion.runtime.tools.web_search import WebSearchTool
from orion.runtime.tools.write_file import WriteFileTool

# ── R-12: "~" é expandido pelas tools de escrita ──────────────────────────────


async def test_write_and_edit_expand_tilde(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    result = await WriteFileTool().run(path="~/note.txt", content="a")
    assert result.success
    assert (tmp_path / "home" / "note.txt").read_text() == "a"
    assert not (tmp_path / "~").exists()
    edit = await EditFileTool().run(path="~/note.txt", target="a", replacement="b")
    assert edit.success and (tmp_path / "home" / "note.txt").read_text() == "b"


# ── R-03/R-10: 429 momentâneo retenta; cota diária não ──────────────────────────


def _resp(headers: dict[str, str], body: str) -> httpx.Response:
    return httpx.Response(429, headers=headers, text=body)


def test_rate_limit_message_has_no_none_and_retries_transient() -> None:
    err = OpenRouterProvider._raise_for_status
    with pytest.raises(RateLimitError) as exc:
        err(_resp({"Retry-After": "7"}, "{}"))
    assert "None" not in str(exc.value) and exc.value.retry_after == 7.0
    assert is_retryable(exc.value) and not exc.value.quota_exhausted


def test_daily_quota_is_not_retried_and_says_when_it_renews() -> None:
    import time

    reset_ms = int((time.time() + 5 * 3600) * 1000)
    body = json.dumps(
        {
            "error": {
                "message": "Rate limit exceeded: free-models-per-day",
                "metadata": {"headers": {"X-RateLimit-Reset": str(reset_ms)}},
            }
        }
    )
    with pytest.raises(RateLimitError) as exc:
        OpenRouterProvider._raise_for_status(_resp({}, body))
    assert exc.value.quota_exhausted and not is_retryable(exc.value)
    assert "cota diária" in str(exc.value) and "Renova" in str(exc.value)


# ── R-13: bloqueio anti-bot não vira "(no results)" ───────────────────────────


async def test_web_search_reports_antibot_challenge() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(202, text="<html>anomaly</html>"))
    result = await WebSearchTool(transport=transport).run(query="dólar")
    assert not result.success and "anti-bot" in result.error


# ── R-08: recall sem ruído ──────────────────────────────────────────────────


def test_recall_noise_filter() -> None:
    q = "apague tudo do orion-sandbox com rm -rf"
    assert _is_noise("olá", q)
    assert _is_noise("não tem ninguem aí?", q)
    assert _is_noise("Destile a solução desta sessão em uma skill reutilizável", q)
    assert not _is_noise("O orion-sandbox fica em ~/orion-sandbox e foi criado com rm -rf antes", q)


# ── R-11: breaker acompanha o modelo fixado ──────────────────────────────────


def test_breaker_primary_follows_selected_model(tmp_path: Path) -> None:
    from orion.tui.session import AgentSession
    from orion.tui.sink import NullSink

    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "k"}):
        session = AgentSession(workspace=tmp_path, home=tmp_path / "home", sink=NullSink())
        session.set_model("google/gemma-4-31b-it:free")
        assert session.breaker.primary_model_id == "google/gemma-4-31b-it:free"
        assert session.breaker.primary_model_tier == ComplexityTier.BALANCED
        session.set_model(None)
        assert session.breaker.primary_model_id == session.router.tier_model(ComplexityTier.HEAVY)
        session.shutdown()


# ── chave do OpenRouter por arquivo ───────────────────────────────────────────


def test_openrouter_key_env_wins_over_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert load_openrouter_key(tmp_path) is None
    (tmp_path / "openrouter_api_key").write_text("from-file\n")
    assert load_openrouter_key(tmp_path) == "from-file"
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-env")
    assert load_openrouter_key(tmp_path) == "from-env"


# ── R-04: o agente não altera arquivos de governança ─────────────────────────


def _pep(tmp_path: Path) -> PolicyEnforcementPoint:
    return PolicyEnforcementPoint(
        scope=WorkspaceScope(roots=[tmp_path]),
        audit_logger=AuditLogger(log_path=tmp_path / "audit.log"),
        mode=AutonomyMode.FULLY_AUTO,
        confirm=lambda _: True,
    )


def test_protected_state_paths(tmp_path: Path) -> None:
    home = tmp_path / ".orion"
    assert is_protected_state_path(str(home / "web_allowlist.json"), home)
    assert is_protected_state_path(str(home / "audit.log"), home)
    assert is_protected_state_path(str(home / "secrets" / "telegram_token"), home)
    assert not is_protected_state_path(str(home / "notes.md"), home)
    assert not is_protected_state_path(str(tmp_path / "web_allowlist.json"), home)


async def test_pep_denies_agent_write_to_allowlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".orion").mkdir()
    pep = _pep(tmp_path)
    action = Action(
        tool="write_file",
        params={"path": "~/.orion/web_allowlist.json", "content": "{}"},
        risk_level=RiskLevel.SAFE,
    )
    with pytest.raises(ActionDenied, match="governança"):
        await pep.evaluate(action)
    entries = [json.loads(line) for line in (tmp_path / "audit.log").read_text().splitlines()]
    assert any(e.get("denial_reason") == "protected_governance_file" for e in entries)


# ── R-14: a auditoria registra o step-up nuclear ─────────────────────────────


async def test_audit_records_nuclear_stepup(tmp_path: Path) -> None:
    gate = NuclearSafetyGate()
    pep = PolicyEnforcementPoint(
        scope=WorkspaceScope(roots=[tmp_path]),
        audit_logger=AuditLogger(log_path=tmp_path / "audit.log"),
        mode=AutonomyMode.FULLY_AUTO,
        nuclear_gate=gate,
    )
    action = Action(
        tool="run_command", params={"command": "rm -rf /tmp/x"}, risk_level=RiskLevel.SAFE
    )
    result = NuclearChallengeResult(
        authorized=True,
        method_used="zenity",
        duration_seconds=2.0,
        command_pattern="rm -rf /tmp/x",
        blast_radius=BlastRadius.NUCLEAR_DESTRUCTIVE,
    )
    with patch.object(gate, "challenge", return_value=result):
        assert await pep.evaluate(action)
    last = [json.loads(line) for line in (tmp_path / "audit.log").read_text().splitlines()][-1]
    assert last["user_authorized"] is True
    assert last["decision_source"].startswith("nuclear_stepup:zenity")
