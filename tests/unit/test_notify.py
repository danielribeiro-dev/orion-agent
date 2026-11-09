"""Testes do módulo notify: Inbox, desktop, Telegram e roteador (Sprint 7)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from orion.notify.desktop import DesktopNotifier, SubprocessRunner
from orion.notify.inbox import Inbox
from orion.notify.models import (
    DEFAULT_DELIVERY,
    Delivery,
    FeedbackEvent,
    NotifyAction,
    OutgoingMessage,
)
from orion.notify.router import OutputRouter
from orion.notify.telegram import TelegramNotifier, load_telegram_token

TOKEN = "123456:SECRET-TOKEN-XYZ"
APPROVE = [NotifyAction(id="approve", label="Aprovar"), NotifyAction(id="deny", label="Negar")]


def _msg(**kw: Any) -> OutgoingMessage:
    kw.setdefault("title", "Titulo")
    return OutgoingMessage(**kw)


@pytest.fixture
def inbox(tmp_path: Path) -> Iterator[Inbox]:
    box = Inbox(tmp_path / "inbox.db")
    yield box
    box.close()


# ------------------------------------------------------------------- Inbox


def test_inbox_file_mode_and_lifecycle(inbox: Inbox, tmp_path: Path) -> None:
    assert (tmp_path / "inbox.db").stat().st_mode & 0o777 == 0o600
    m = _msg(body="corpo", actions=APPROVE, payload={"k": 1})
    inbox.add(m)
    item = inbox.get(m.id)
    assert item is not None and item.status == "pending" and item.payload == {"k": 1}
    assert item.actions[0].id == "approve" and item.expires_at is None
    assert inbox.pending_count() == 1
    assert inbox.get("nope") is None
    inbox.mark_read(m.id)
    got = inbox.get(m.id)
    assert got is not None and got.status == "read"
    assert inbox.pending_count() == 0


def test_inbox_list_filter_and_order(inbox: Inbox) -> None:
    a = _msg(created_at=datetime(2026, 1, 1, tzinfo=UTC))
    b = _msg(created_at=datetime(2026, 1, 2, tzinfo=UTC))
    inbox.add(a)
    inbox.add(b, status="read")
    assert [i.id for i in inbox.list()] == [b.id, a.id]
    assert [i.id for i in inbox.list(status="pending")] == [a.id]
    assert len(inbox.list(limit=1)) == 1


def test_resolve_once(inbox: Inbox) -> None:
    m = _msg(actions=APPROVE)
    inbox.add(m)
    assert inbox.resolve(m.id, "approve", "desktop") is True
    assert inbox.resolve(m.id, "deny", "telegram") is False
    item = inbox.get(m.id)
    assert item is not None
    assert (item.status, item.resolution, item.resolved_by) == ("resolved", "approve", "desktop")
    assert inbox.resolve("missing", "x", "y") is False


def test_expiry(tmp_path: Path) -> None:
    now = datetime(2026, 5, 1, tzinfo=UTC)
    box = Inbox(tmp_path / "e.db", clock=lambda: now + timedelta(seconds=100))
    m = _msg(ttl_s=60, created_at=now)
    keep = _msg(ttl_s=600, created_at=now)
    box.add(m)
    box.add(keep)
    assert box.resolve(m.id, "approve", "x") is False  # expirou no relógio injetado
    got = box.get(m.id)
    assert got is not None and got.status == "expired"
    other = _msg(ttl_s=10, created_at=now)
    box.add(other)
    assert box.expire_due(now + timedelta(seconds=50)) == [other.id]
    assert box.expire(keep.id) is True
    assert box.expire(keep.id) is False


async def test_wait_resolution(inbox: Inbox) -> None:
    m = _msg()
    inbox.add(m)
    waiter = asyncio.create_task(inbox.wait_resolution(m.id, 5))
    await asyncio.sleep(0.05)
    inbox.resolve(m.id, "approve", "client")
    item = await waiter
    assert item is not None and item.resolution == "approve"
    # já resolvido: retorna na hora
    assert await inbox.wait_resolution(m.id, 0.1) is not None


async def test_wait_resolution_timeout_and_thread(inbox: Inbox) -> None:
    m = _msg()
    inbox.add(m)
    assert await inbox.wait_resolution(m.id, 0.05) is None
    waiter = asyncio.create_task(inbox.wait_resolution(m.id, 5))
    await asyncio.sleep(0.05)
    t = threading.Thread(target=inbox.resolve, args=(m.id, "deny", "thread"))
    t.start()
    t.join()
    item = await waiter
    assert item is not None and item.resolved_by == "thread"


async def test_wait_resolution_expired(inbox: Inbox) -> None:
    m = _msg()
    inbox.add(m)
    waiter = asyncio.create_task(inbox.wait_resolution(m.id, 5))
    await asyncio.sleep(0.05)
    inbox.expire(m.id)
    item = await waiter
    assert item is not None and item.status == "expired"


def test_hold_and_feedback(inbox: Inbox) -> None:
    a, b = _msg(title="A"), _msg(title="B")
    inbox.hold(a)
    inbox.hold(b)
    assert [m.title for m in inbox.take_held()] == ["A", "B"]
    assert inbox.take_held() == []
    inbox.record_feedback(FeedbackEvent(message_id="1", signal="approved", channel="notify"))
    inbox.record_feedback(
        FeedbackEvent(message_id="2", signal="denied", channel="inbox", rule_key="r")
    )
    fb = inbox.feedback()
    assert [f.message_id for f in fb] == ["2", "1"] and fb[0].rule_key == "r"
    assert len(inbox.feedback(limit=1)) == 1
    inbox.close()


# ----------------------------------------------------------------- Desktop


class FakeRunner:
    def __init__(self, result: tuple[int, str] = (0, ""), exc: Exception | None = None) -> None:
        self.calls: list[tuple[list[str], float | None]] = []
        self.result = result
        self.exc = exc

    async def run(self, argv: list[str], timeout_s: float | None) -> tuple[int, str]:
        self.calls.append((argv, timeout_s))
        if self.exc:
            raise self.exc
        return self.result


def test_desktop_argv() -> None:
    d = DesktopNotifier(FakeRunner(), available=True)
    m = _msg(title="T", body="<b>x</b> & y", priority="critical", actions=APPROVE)
    argv = d.build_argv(m, Delivery(silent=True), wait=True, expire_ms=5000)
    assert argv[0] == "notify-send" and "--urgency=critical" in argv
    assert "--hint=boolean:suppress-sound:true" in argv and "--wait" in argv
    assert "--action=approve=Aprovar" in argv and "--expire-time=5000" in argv
    assert argv[-1] == "&lt;b&gt;x&lt;/b&gt; &amp; y" and argv[-3] == "--"
    for prio, urg in (("high", "normal"), ("low", "low")):
        a = d.build_argv(_msg(priority=prio), DEFAULT_DELIVERY, wait=False)  # type: ignore[arg-type]
        assert f"--urgency={urg}" in a
        assert "--wait" not in a and not any("suppress" in x for x in a)


def test_desktop_truncates() -> None:
    d = DesktopNotifier(FakeRunner(), available=True)
    argv = d.build_argv(_msg(title="t" * 500, body="b" * 5000), DEFAULT_DELIVERY, wait=False)
    assert len(argv[-2]) <= 100 and len(argv[-1]) <= 500


async def test_desktop_show_and_ask() -> None:
    r = FakeRunner((0, "approve\n"))
    d = DesktopNotifier(r, available=True)
    await d.show(_msg(), DEFAULT_DELIVERY)
    assert "--wait" not in r.calls[0][0]
    assert await d.ask(_msg(actions=APPROVE), DEFAULT_DELIVERY, 30) == "approve"
    assert r.calls[1][1] == 30 and "--expire-time=30000" in r.calls[1][0]


async def test_desktop_ask_none_cases() -> None:
    m = _msg(actions=APPROVE)
    assert await DesktopNotifier(FakeRunner((0, ""))).ask(m, DEFAULT_DELIVERY, 1) is None
    assert await DesktopNotifier(FakeRunner((1, "approve"))).ask(m, DEFAULT_DELIVERY, 1) is None
    assert await DesktopNotifier(FakeRunner((0, "hack"))).ask(m, DEFAULT_DELIVERY, 1) is None
    assert (
        await DesktopNotifier(FakeRunner(exc=TimeoutError())).ask(m, DEFAULT_DELIVERY, 1) is None
    )
    await DesktopNotifier(FakeRunner(exc=FileNotFoundError())).show(m, DEFAULT_DELIVERY)


async def test_subprocess_runner() -> None:
    code, out = await SubprocessRunner().run(["/bin/echo", "oi"], 5)
    assert (code, out.strip()) == (0, "oi")
    with pytest.raises(TimeoutError):
        await SubprocessRunner().run(["/bin/sleep", "5"], 0.1)


def test_desktop_available(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    d = DesktopNotifier()
    monkeypatch.setattr("shutil.which", lambda _n: None)
    assert d.available() is False
    monkeypatch.setattr("shutil.which", lambda _n: "/usr/bin/notify-send")
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/x")
    assert d.available() is True
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS")
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    assert d.available() is False
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert d.available() is False
    (tmp_path / "bus").touch()
    assert d.available() is True


# ---------------------------------------------------------------- Telegram


class FakeTelegram:
    """Servidor Bot API falso sobre httpx.MockTransport."""

    def __init__(self, updates: list[list[dict[str, Any]]] | None = None, fail: bool = False):
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.updates = updates or []
        self.fail = fail

    def handler(self, request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        body = json.loads(request.content) if request.content else {}
        self.requests.append((method, body))
        if self.fail:
            return httpx.Response(500, json={"ok": False})
        if method == "sendMessage":
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 77}})
        if method == "getUpdates":
            res = self.updates.pop(0) if self.updates else []
            return httpx.Response(200, json={"ok": True, "result": res})
        return httpx.Response(200, json={"ok": True, "result": True})

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))

    def methods(self) -> list[str]:
        return [m for m, _ in self.requests]


def _cb(msg_id: str, action: str, sender: int = 42, uid: int = 1) -> dict[str, Any]:
    return {
        "update_id": uid,
        "callback_query": {"id": "cb1", "from": {"id": sender}, "data": f"{msg_id}:{action}"},
    }


async def test_telegram_send_payload() -> None:
    fake = FakeTelegram()
    tg = TelegramNotifier(TOKEN, 42, http=fake.client())
    m = _msg(title="T", body="B", actions=APPROVE)
    assert await tg.send(m, Delivery(silent=True)) == 77
    method, body = fake.requests[0]
    assert method == "sendMessage" and body["chat_id"] == 42
    assert body["disable_notification"] is True and body["text"] == "T\n\nB"
    kb = body["reply_markup"]["inline_keyboard"][0]
    assert kb[0]["callback_data"] == f"{m.id}:approve"
    await tg.send(_msg(), DEFAULT_DELIVERY)
    assert "reply_markup" not in fake.requests[1][1]
    await tg.aclose()


async def test_telegram_ask_owner_only() -> None:
    m = _msg(actions=APPROVE)
    fake = FakeTelegram(
        updates=[
            [_cb(m.id, "approve", sender=999, uid=1), _cb("other", "approve", uid=2)],
            [_cb(m.id, "bogus", uid=3), {"update_id": 4, "message": {}}],
            [_cb(m.id, "deny", uid=5)],
        ]
    )
    tg = TelegramNotifier(TOKEN, 42, http=fake.client())
    assert await tg.ask(m, DEFAULT_DELIVERY, 30) == "deny"
    assert "answerCallbackQuery" in fake.methods()
    edit = next(b for meth, b in fake.requests if meth == "editMessageText")
    assert "Decisão: Negar" in edit["text"] and edit["message_id"] == 77
    offsets = [b["offset"] for meth, b in fake.requests if meth == "getUpdates"]
    assert offsets == [0, 3, 5]


async def test_telegram_ask_ttl_and_errors() -> None:
    m = _msg(actions=APPROVE)
    fake = FakeTelegram()
    tg = TelegramNotifier(TOKEN, 42, http=fake.client())
    assert await tg.ask(m, DEFAULT_DELIVERY, 0.2) is None
    bad = FakeTelegram(fail=True)
    assert await TelegramNotifier(TOKEN, 42, http=bad.client()).ask(m, DEFAULT_DELIVERY, 5) is None

    def boom(_r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("falhou")

    tg2 = TelegramNotifier(
        TOKEN, 42, http=httpx.AsyncClient(transport=httpx.MockTransport(boom))
    )
    assert await tg2.send(m, DEFAULT_DELIVERY) is None

    def junk(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="nao e json")

    tg3 = TelegramNotifier(TOKEN, 42, http=httpx.AsyncClient(transport=httpx.MockTransport(junk)))
    assert await tg3.send(m, DEFAULT_DELIVERY) is None

    # getUpdates falha depois do send
    state = {"n": 0}

    def flaky(r: httpx.Request) -> httpx.Response:
        state["n"] += 1
        if r.url.path.endswith("sendMessage"):
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
        return httpx.Response(502, json={"ok": False})

    tg4 = TelegramNotifier(TOKEN, 42, http=httpx.AsyncClient(transport=httpx.MockTransport(flaky)))
    assert await tg4.ask(m, DEFAULT_DELIVERY, 5) is None


async def test_telegram_token_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)

    def boom(_r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("falhou")

    for handler in (boom, FakeTelegram(fail=True).handler, FakeTelegram().handler):
        tg = TelegramNotifier(
            TOKEN, 42, http=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        )
        await tg.send(_msg(actions=APPROVE), DEFAULT_DELIVERY)
    assert caplog.records
    assert "SECRET-TOKEN" not in caplog.text
    assert "SECRET-TOKEN" not in repr(caplog.records)


def test_load_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("ORION_TELEGRAM_TOKEN", raising=False)
    assert load_telegram_token(tmp_path) is None
    sec = tmp_path / "secrets"
    sec.mkdir()
    f = sec / "telegram_token"
    f.write_text(TOKEN + "\n")
    os.chmod(f, 0o644)
    assert load_telegram_token(tmp_path) is None
    assert "SECRET-TOKEN" not in caplog.text and "permissões" in caplog.text
    os.chmod(f, 0o600)
    assert load_telegram_token(tmp_path) == TOKEN
    f.write_text("  \n")
    assert load_telegram_token(tmp_path) is None
    monkeypatch.setenv("ORION_TELEGRAM_TOKEN", "envtok")
    assert load_telegram_token(tmp_path) == "envtok"


# ------------------------------------------------------------------ Router


class FakeClients:
    def __init__(self, present: bool = True) -> None:
        self.present = present
        self.delivered: list[str] = []

    def has_clients(self) -> bool:
        return self.present

    async def deliver(self, message: OutgoingMessage, delivery: Delivery) -> None:
        self.delivered.append(message.id)


class FakeDesktop(DesktopNotifier):
    def __init__(self, ok: bool = True, answer: str | None = None, delay: float = 0.0) -> None:
        super().__init__(FakeRunner(), available=ok)
        self.shown: list[str] = []
        self.answer = answer
        self.delay = delay

    async def show(self, msg: OutgoingMessage, delivery: Delivery) -> None:
        self.shown.append(msg.id)

    async def ask(self, msg: OutgoingMessage, delivery: Delivery, timeout_s: float) -> str | None:
        await asyncio.sleep(self.delay)
        return self.answer


class FakeTg(TelegramNotifier):
    def __init__(self, answer: str | None = None, delay: float = 0.0) -> None:
        super().__init__(TOKEN, 42, http=FakeTelegram().client())
        self.sent: list[str] = []
        self.answer = answer
        self.delay = delay
        self.cancelled = False

    async def send(self, msg: OutgoingMessage, delivery: Delivery) -> int | None:
        self.sent.append(msg.id)
        return 1

    async def ask(self, msg: OutgoingMessage, delivery: Delivery, timeout_s: float) -> str | None:
        try:
            await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return self.answer


class FakePresence:
    def __init__(self, delivery: Delivery) -> None:
        self.delivery = delivery

    def decide(self, message: OutgoingMessage, now: datetime) -> Delivery:
        return self.delivery


async def test_router_client_first(inbox: Inbox) -> None:
    clients, desk, tg = FakeClients(), FakeDesktop(), FakeTg()
    r = OutputRouter(inbox=inbox, clients=clients, desktop=desk, telegram=tg)
    m = _msg()
    res = await r.send(m)
    assert res.channels == ["client"] and clients.delivered == [m.id]
    assert not desk.shown and not tg.sent
    item = inbox.get(m.id)
    assert item is not None and item.status == "read"


async def test_router_desktop_then_telegram(inbox: Inbox) -> None:
    desk, tg = FakeDesktop(), FakeTg()
    r = OutputRouter(inbox=inbox, clients=FakeClients(False), desktop=desk, telegram=tg)
    res = await r.send(_msg())
    assert res.channels == ["desktop"] and not tg.sent
    item = inbox.list()[0]
    assert item.status == "pending"
    res = await r.send(_msg(priority="high"))
    assert res.channels == ["desktop", "telegram"]
    # desktop indisponível: Telegram assume
    tg2 = FakeTg()
    r2 = OutputRouter(inbox=inbox, desktop=FakeDesktop(ok=False), telegram=tg2)
    assert (await r2.send(_msg())).channels == ["telegram"]
    # nada configurado: só Inbox
    r3 = OutputRouter(inbox=inbox)
    assert (await r3.send(_msg())).channels == []


async def test_router_cap_enforced(inbox: Inbox) -> None:
    desk, tg, clients = FakeDesktop(), FakeTg(), FakeClients(False)
    gate = FakePresence(Delivery(channel_cap="none"))
    r = OutputRouter(inbox=inbox, presence=gate, clients=clients, desktop=desk, telegram=tg)
    m = _msg(priority="critical")
    res = await r.send(m)
    assert res.channels == [] and not desk.shown and not tg.sent
    assert inbox.get(m.id) is not None  # ledger silencioso
    gate.delivery = Delivery(channel_cap="inbox")
    assert (await r.send(_msg())).channels == []
    clients.present = True
    assert (await r.send(_msg())).channels == ["client"]


async def test_router_digest_hold_and_flush(inbox: Inbox) -> None:
    desk = FakeDesktop()
    gate = FakePresence(Delivery(digest=True, reason="foco"))
    r = OutputRouter(inbox=inbox, presence=gate, desktop=desk)
    assert await r.flush_digest() is None
    res = await r.send(_msg(title="um"))
    await r.send(_msg(title="dois"))
    assert res.held_for_digest and not desk.shown and inbox.list() == []
    out = await r.flush_digest()  # presença ainda em digest: não segura de novo
    assert out is not None and not out.held_for_digest and out.channels == ["desktop"]
    assert inbox.take_held() == []
    item = inbox.list()[0]
    assert item.kind == "digest" and item.title == "Resumo: 2 itens"
    assert "- um" in item.body and "- dois" in item.body


async def test_approval_via_desktop(inbox: Inbox) -> None:
    tg = FakeTg(delay=5)
    r = OutputRouter(
        inbox=inbox, desktop=FakeDesktop(answer="approve", delay=0.01), telegram=tg
    )
    m = _msg(kind="approval", actions=APPROVE)
    res = await r.request_approval(m, ttl_s=5)
    assert res.approved and res.channel == "desktop" and res.action_id == "approve"
    item = inbox.get(m.id)
    assert item is not None and item.status == "resolved" and item.resolved_by == "desktop"
    assert tg.cancelled
    assert inbox.feedback()[0].signal == "approved"
    assert inbox.feedback()[0].channel == "notify"


async def test_approval_deny_telegram(inbox: Inbox) -> None:
    r = OutputRouter(
        inbox=inbox,
        presence=FakePresence(Delivery(rule_key="rk")),
        desktop=FakeDesktop(answer=None, delay=0.01),
        telegram=FakeTg(answer="deny", delay=0.05),
    )
    res = await r.request_approval(_msg(actions=APPROVE), ttl_s=5)
    assert not res.approved and res.channel == "telegram" and res.action_id == "deny"
    fb = inbox.feedback()[0]
    assert fb.signal == "denied" and fb.rule_key == "rk"


async def test_approval_via_inbox_resolution(inbox: Inbox) -> None:
    clients = FakeClients()
    r = OutputRouter(inbox=inbox, clients=clients, desktop=FakeDesktop(delay=5))
    m = _msg(actions=APPROVE)

    async def later() -> None:
        await asyncio.sleep(0.1)
        inbox.resolve(m.id, "approve", "client")

    t = asyncio.create_task(later())
    res = await r.request_approval(m, ttl_s=5)
    await t
    assert res.approved and res.channel == "client"
    assert clients.delivered == [m.id]
    assert inbox.feedback()[0].channel == "inbox"


async def test_approval_expires(inbox: Inbox) -> None:
    r = OutputRouter(inbox=inbox, telegram=FakeTg(delay=5))
    m = _msg(actions=APPROVE)
    res = await r.request_approval(m, ttl_s=1)
    assert not res.approved and res.action_id is None
    item = inbox.get(m.id)
    assert item is not None and item.status == "expired"
    assert inbox.feedback()[0].signal == "expired"


async def test_approval_dismissed(inbox: Inbox) -> None:
    r = OutputRouter(inbox=inbox, desktop=FakeDesktop(answer=None))
    res = await r.request_approval(_msg(actions=APPROVE), ttl_s=1)
    assert not res.approved
    assert inbox.feedback()[0].signal == "dismissed"


async def test_approval_nuclear_refused(inbox: Inbox) -> None:
    desk, tg = FakeDesktop(answer="approve"), FakeTg(answer="approve")
    r = OutputRouter(inbox=inbox, desktop=desk, telegram=tg)
    m = _msg(actions=APPROVE, payload={"nuclear": True})
    res = await r.request_approval(m, ttl_s=5)
    assert not res.approved and res.reason == "aprovação nuclear remota é proibida"
    assert not tg.sent and not desk.shown
    item = inbox.get(m.id)
    assert item is not None and item.status == "expired"
    assert inbox.feedback()[0].signal == "denied"


async def test_approval_channel_exception_and_cap(inbox: Inbox) -> None:
    class Boom(FakeTg):
        async def ask(self, msg: OutgoingMessage, delivery: Delivery, t: float) -> str | None:
            raise RuntimeError("x")

    r = OutputRouter(inbox=inbox, telegram=Boom())
    assert not (await r.request_approval(_msg(actions=APPROVE), ttl_s=1)).approved
    # cap inbox: nenhum canal de push é consultado
    desk = FakeDesktop(answer="approve")
    r2 = OutputRouter(
        inbox=inbox, presence=FakePresence(Delivery(channel_cap="inbox")), desktop=desk
    )
    res = await r2.request_approval(_msg(actions=APPROVE), ttl_s=1)
    assert not res.approved
