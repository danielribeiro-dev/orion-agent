"""v0.5.3 Sprint 1 — superfícies do Senhor: ``orion setup sudo``, ``/web``, senha mascarada e ``/doctor``."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from orion.governance import sudo_setup
from orion.governance.askpass import SUDO_KEYRING_MARKER, SecretRequest
from orion.tui import modal
from orion.tui.commands.base import CommandContext

from .test_screen_app import running, settle, text_of


class Store:
    def __init__(self, secret: str | None = None, fail: bool = False) -> None:
        self.secret = secret
        self.fail = fail

    def get(self) -> str | None:
        return self.secret

    def set(self, secret: str) -> None:
        if self.fail:
            raise RuntimeError("trancado")
        self.secret = secret

    def delete(self) -> bool:
        had = self.secret is not None
        self.secret = None
        return had


# ── orion setup sudo ─────────────────────────────────────────────────────────


class TestSetupSudo:
    def test_right_password_is_kept_in_the_keyring_only(self, tmp_path: Path) -> None:
        store = Store()
        out = sudo_setup.remember(tmp_path, store=store, read_secret=lambda _p: "certa", verify=lambda s: s == "certa")
        assert out.code == 0 and store.secret == "certa"
        marker = tmp_path / SUDO_KEYRING_MARKER
        assert marker.read_text() == "keyring\n" and oct(marker.stat().st_mode)[-3:] == "600"
        assert all("certa" not in p.read_text(errors="ignore") for p in tmp_path.rglob("*") if p.is_file())

    def test_wrong_password_is_never_stored(self, tmp_path: Path) -> None:
        store = Store()
        out = sudo_setup.remember(tmp_path, store=store, read_secret=lambda _p: "errada", verify=lambda s: False)
        assert out.code == 1 and store.secret is None and not (tmp_path / SUDO_KEYRING_MARKER).exists()

    def test_empty_and_locked_keyring(self, tmp_path: Path) -> None:
        assert sudo_setup.remember(tmp_path, store=Store(), read_secret=lambda _p: "", verify=lambda s: True).code == 1
        out = sudo_setup.remember(tmp_path, store=Store(fail=True), read_secret=lambda _p: "x", verify=lambda s: True)
        assert out.code == 1 and "chaveiro" in out.lines[0]

    def test_forget(self, tmp_path: Path) -> None:
        store = Store("x")
        (tmp_path / SUDO_KEYRING_MARKER).write_text("keyring\n")
        assert sudo_setup.forget(tmp_path, store=store).code == 0
        assert store.secret is None and not (tmp_path / SUDO_KEYRING_MARKER).exists()
        assert "não havia" in sudo_setup.forget(tmp_path, store=Store()).lines[0]

    def test_sudoers_draft_and_apply(self, tmp_path: Path) -> None:
        out = sudo_setup.sudoers_draft(tmp_path)
        draft = tmp_path / sudo_setup.SUDOERS_DRAFT
        assert out.code == 0 and "NOPASSWD: /usr/bin/apt update" in draft.read_text()
        calls: list[list[str]] = []

        def runner(argv: list[str]) -> int:
            calls.append(argv)
            return 0

        assert sudo_setup.sudoers_apply(tmp_path, runner=runner).code == 0
        assert calls[0][1:3] == ["-c", "-f"]
        assert calls[1][1:] == ["install", "-m", "0440", "-o", "root", "-g", "root", str(draft), "/etc/sudoers.d/orion"]

    @pytest.mark.parametrize(
        "rule",
        ["u ALL=(ALL) NOPASSWD: ALL", "u ALL=(root) NOPASSWD: /bin/bash", "u ALL=(ALL) ALL", "u ALL=NOPASSWD: /usr/bin/env x"],
    )
    def test_apply_refuses_blanket_rules(self, tmp_path: Path, rule: str) -> None:
        (tmp_path / sudo_setup.SUDOERS_DRAFT).write_text(rule + "\n")
        out = sudo_setup.sudoers_apply(tmp_path, runner=lambda argv: 0)
        assert out.code == 1 and "ALL" in out.lines[0]

    def test_apply_stops_when_visudo_refuses_or_missing_draft(self, tmp_path: Path) -> None:
        assert sudo_setup.sudoers_apply(tmp_path, runner=lambda a: 0).code == 1
        sudo_setup.sudoers_draft(tmp_path)
        assert "visudo" in sudo_setup.sudoers_apply(tmp_path, runner=lambda a: 1).lines[0]

    def test_run_requires_terminal_to_remember(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("os.isatty", lambda fd: False)
        assert sudo_setup.run(tmp_path).code == 2

    def test_cli_is_registered(self) -> None:
        from typer.testing import CliRunner

        from orion.cli import app

        result = CliRunner().invoke(app, ["setup", "sudo", "--help"])
        assert result.exit_code == 0 and "--forget" in result.output


# ── /web ─────────────────────────────────────────────────────────────────────


class FakeSessionHome:
    def __init__(self, home: Path) -> None:
        self.home = home


async def run_web(tmp_path: Path, args: str) -> tuple[Any, str]:
    from orion.tui.commands.operation import WebCommand

    console = Console(record=True, width=100)
    result = await WebCommand().execute(args, CommandContext(FakeSessionHome(tmp_path), console, lambda: None))
    return result, console.export_text()


class TestWebCommand:
    async def test_block_list_unblock(self, tmp_path: Path) -> None:
        from orion.runtime.tools.web_policy import load_blocklist

        _, text = await run_web(tmp_path, "list")
        assert "web aberta" in text
        result, text = await run_web(tmp_path, "block https://Spam.Example/x")
        assert result.success and load_blocklist(tmp_path) == ("spam.example",)
        _, text = await run_web(tmp_path, "")
        assert "spam.example" in text
        result, _ = await run_web(tmp_path, "unblock spam.example")
        assert result.success and load_blocklist(tmp_path) == ()
        result, text = await run_web(tmp_path, "unblock spam.example")
        assert "não estava" in text

    async def test_invalid_input(self, tmp_path: Path) -> None:
        result, text = await run_web(tmp_path, "block localhost")
        assert not result.success and "inválido" in text
        result, text = await run_web(tmp_path, "explode")
        assert not result.success and "uso" in text


# ── Senha mascarada na tela cheia (nunca no histórico nem na transcrição) ────


@pytest.mark.asyncio
async def test_fullscreen_secret_is_masked_and_never_saved(tmp_path: Path) -> None:
    async with running(tmp_path) as (screen, _session, send):
        request = SecretRequest("sudo", "sudo apt update", "[sudo] senha:")
        answer = asyncio.ensure_future(modal.ask_secret(Console(), request))
        await settle()
        assert screen._secret
        send("s3gr3d0-xyz")
        await settle()
        rendered = "".join(t for _s, t in screen._input_window.content.create_content(80, 5).get_line(0))
        assert "s3gr3d0" not in rendered and "*" * 11 in rendered
        assert rendered.startswith("› ")  # o prefixo nunca é mascarado
        send("\r")
        assert await asyncio.wait_for(answer, 2) == "s3gr3d0-xyz"
        await settle()
        assert not screen._secret and screen.buffer.text == ""
        assert "sudo apt update" in text_of(screen) and "s3gr3d0" not in text_of(screen)
        assert "s3gr3d0" not in list(screen.buffer.history.get_strings())
        history_file = tmp_path / "history"
        assert not history_file.exists() or "s3gr3d0" not in history_file.read_text()


@pytest.mark.asyncio
async def test_fullscreen_secret_escape_cancels(tmp_path: Path) -> None:
    async with running(tmp_path) as (screen, _session, send):
        answer = asyncio.ensure_future(modal.ask_secret(Console(), SecretRequest("nuclear", "rm -rf x", "")))
        await settle()
        send("abc\x1b")
        assert await asyncio.wait_for(answer, 3) is None
        assert not screen._secret


async def test_ask_secret_without_terminal_or_display_returns_none() -> None:
    # Sem host, sem TTY e com o popup bloqueado (conftest): ninguém para responder.
    assert await modal.ask_secret(Console(), SecretRequest("sudo", "sudo x", "")) is None


def test_secret_request_titles() -> None:
    assert "irreversível" in SecretRequest("nuclear", "x", "").title
    assert SecretRequest("sudo", "x", "", attempt=2).title.endswith("(tentativa 2 de 3)")


async def test_doctor_reports_freedom_checks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from orion.tui.commands.operation import _freedom_checks

    (tmp_path / "web_allowlist.json").write_text("{}")
    (tmp_path / ".env").write_text("BRAVE_API_KEY=x\n")
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    names = {name: detail for name, _ok, detail in _freedom_checks(tmp_path)}
    assert "sudo (askpass)" in names and "Presença nuclear" in names
    assert "Allowlist antiga" in names and names["Busca web"].startswith("brave")
    assert "não" in names["Senha do sudo lembrada"]
