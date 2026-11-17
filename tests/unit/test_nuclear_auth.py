"""v0.5.3 Sprint 1 — presença nuclear verificada (ADR-048, G-01, G-03): CA-07 (parte).

polkit e PAM são simulados: nenhum diálogo real abre e nenhuma senha real é tentada.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from orion.core.events import Action, RiskLevel
from orion.governance.askpass import SecretRequest
from orion.governance.audit import AuditLogger
from orion.governance.nuclear import BlastRadius, NuclearSafetyGate
from orion.governance.pep import ActionDenied, AutonomyMode, PolicyEnforcementPoint
from orion.governance.permissions import WorkspaceScope

NUCLEAR = "rm -rf /tmp/orion-test-nunca"


class FakeProc:
    def __init__(self, rc: int, err: bytes = b"") -> None:
        self.returncode = rc
        self._err = err

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", self._err


def spawn(rc: int, err: bytes = b"") -> Any:
    calls: list[tuple[Any, ...]] = []

    async def fake(*args: Any, **kwargs: Any) -> FakeProc:
        calls.append(args)
        return FakeProc(rc, err)

    fake.calls = calls  # type: ignore[attr-defined]
    return fake


def prompter(answer: str | None) -> Any:
    seen: list[SecretRequest] = []

    async def ask(request: SecretRequest) -> str | None:
        seen.append(request)
        return answer

    ask.seen = seen  # type: ignore[attr-defined]
    return ask


@pytest.fixture()
def display(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISPLAY", ":0")


@pytest.fixture()
def no_display(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)


def which(found: str | None) -> Any:
    return patch("orion.governance.nuclear.shutil.which", side_effect=lambda name: found if name == "pkexec" else None)


class TestPolkit:
    async def test_polkit_success(self, display: None) -> None:
        notes: list[str] = []
        gate = NuclearSafetyGate(notifier=notes.append)
        fake = spawn(0)
        with which("/usr/bin/pkexec"), patch("asyncio.create_subprocess_exec", fake):
            result = await gate.challenge_async(NUCLEAR)
        assert result.authorized and result.method_used == "polkit"
        assert fake.calls[0][:3] == ("/usr/bin/pkexec", "--disable-internal-agent", "/bin/true")
        assert notes and NUCLEAR[:20] in notes[0]

    @pytest.mark.parametrize("rc", [126, 127, 1])
    async def test_polkit_denied_or_cancelled(self, display: None, rc: int) -> None:
        gate = NuclearSafetyGate(prompter=prompter("nunca-usada"))
        with which("/usr/bin/pkexec"), patch("asyncio.create_subprocess_exec", spawn(rc, b"Not authorized")):
            result = await gate.challenge_async(NUCLEAR)
        assert not result.authorized and result.method_used == "polkit"

    async def test_no_polkit_agent_falls_back_to_pam(self, display: None) -> None:
        ask = prompter("certa")
        gate = NuclearSafetyGate(prompter=ask, authenticator=lambda user, pw: pw == "certa")
        err = b"Error executing command as another user: No authentication agent found."
        with which("/usr/bin/pkexec"), patch("asyncio.create_subprocess_exec", spawn(127, err)):
            result = await gate.challenge_async(NUCLEAR)
        assert result.authorized and result.method_used == "pam"

    async def test_pkexec_crash_falls_back_to_pam(self, display: None) -> None:
        async def boom(*_a: Any, **_k: Any) -> Any:
            raise OSError("exec format error")

        gate = NuclearSafetyGate(prompter=prompter("x"), authenticator=lambda u, p: False)
        with which("/usr/bin/pkexec"), patch("asyncio.create_subprocess_exec", boom):
            result = await gate.challenge_async(NUCLEAR)
        assert result.method_used == "pam" and not result.authorized


class TestPam:
    async def test_right_password_authorizes(self, no_display: None) -> None:
        ask = prompter("certa")
        checked: list[tuple[str, str]] = []

        def auth(user: str, secret: str) -> bool:
            checked.append((user, secret))
            return secret == "certa"

        gate = NuclearSafetyGate(prompter=ask, authenticator=auth)
        result = await gate.challenge_async(NUCLEAR)
        assert result.authorized and result.method_used == "pam"
        assert ask.seen[0].purpose == "nuclear" and ask.seen[0].command == NUCLEAR
        assert checked and checked[0][1] == "certa"

    async def test_any_text_is_no_longer_enough(self, no_display: None) -> None:  # G-01
        gate = NuclearSafetyGate(prompter=prompter("qualquer texto"), authenticator=lambda u, p: False)
        result = await gate.challenge_async(NUCLEAR)
        assert not result.authorized and result.method_used == "pam"

    async def test_cancel_denies(self, no_display: None) -> None:
        called: list[str] = []
        gate = NuclearSafetyGate(prompter=prompter(None), authenticator=lambda u, p: called.append(p) or True)
        result = await gate.challenge_async(NUCLEAR)
        assert not result.authorized and called == []

    async def test_no_interface_and_no_polkit_denies(self, no_display: None) -> None:
        result = await NuclearSafetyGate().challenge_async(NUCLEAR)
        assert not result.authorized and result.method_used == "unavailable"

    async def test_never_touches_dev_tty(self, no_display: None) -> None:  # G-03
        with patch("builtins.open", side_effect=AssertionError("/dev/tty não pode ser aberto")):
            result = await NuclearSafetyGate(prompter=prompter(None)).challenge_async(NUCLEAR)
        assert not result.authorized

    def test_default_pam_service(self) -> None:
        gate = NuclearSafetyGate()
        assert gate._service() in ("orion", "login")
        assert NuclearSafetyGate(pam_service="sudo")._service() == "sudo"

    def test_default_authenticator_uses_python_pam(self) -> None:
        with patch("pam.pam") as factory:
            factory.return_value.authenticate.return_value = True
            assert NuclearSafetyGate(pam_service="login")._pam_authenticate("u", "p")
        factory.return_value.authenticate.assert_called_once_with("u", "p", service="login", resetcreds=False)

    async def test_benign_command_never_asks(self) -> None:
        ask = prompter("x")
        result = await NuclearSafetyGate(prompter=ask).challenge_async("git status")
        assert result.authorized and result.blast_radius == BlastRadius.BENIGN and ask.seen == []

    def test_sync_challenge_outside_loop(self, no_display: None) -> None:
        gate = NuclearSafetyGate(prompter=prompter("certa"), authenticator=lambda u, p: p == "certa")
        assert gate.challenge(NUCLEAR).authorized


class TestPepAudit:
    async def test_wrong_password_is_denied_and_audited(self, tmp_path: Path, no_display: None) -> None:
        audit = AuditLogger(tmp_path / "audit.log")
        gate = NuclearSafetyGate(prompter=prompter("errada"), authenticator=lambda u, p: False)
        pep = PolicyEnforcementPoint(
            scope=WorkspaceScope([tmp_path]), mode=AutonomyMode.FULLY_AUTO, audit_logger=audit, nuclear_gate=gate
        )
        action = Action(tool="run_command", params={"command": NUCLEAR}, risk_level=RiskLevel.CRITICAL)
        with pytest.raises(ActionDenied, match="denied"):
            await pep.evaluate(action)
        text = (tmp_path / "audit.log").read_text()
        records = [json.loads(line) for line in text.splitlines()]
        assert any(r.get("denial_reason", "").startswith("nuclear_stepup:failed:pam") for r in records)
        assert "errada" not in text  # a senha nunca vai para a auditoria (CA-03)

    async def test_right_password_is_audited_as_stepup(self, tmp_path: Path, no_display: None) -> None:
        audit = AuditLogger(tmp_path / "audit.log")
        gate = NuclearSafetyGate(prompter=prompter("certa"), authenticator=lambda u, p: p == "certa")

        def never(action: Action, level: Any) -> bool:
            raise AssertionError("presença verificada não pergunta y/n de novo")

        pep = PolicyEnforcementPoint(
            scope=WorkspaceScope([tmp_path]),
            mode=AutonomyMode.SUPERVISED,
            audit_logger=audit,
            nuclear_gate=gate,
            action_confirm=never,
        )
        action = Action(tool="run_command", params={"command": NUCLEAR}, risk_level=RiskLevel.CRITICAL)
        assert await pep.evaluate(action)
        text = (tmp_path / "audit.log").read_text()
        assert "nuclear_stepup:pam" in text and "certa" not in text
