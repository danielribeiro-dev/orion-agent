"""Testes da política de presença (ADR-036, Sprint 7)."""

from __future__ import annotations

import json
import stat
from collections.abc import Iterator
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from orion.memory.facts_store import FactPoisoningAttempt, FactsStore
from orion.notify.models import DEFAULT_DELIVERY, OutgoingMessage
from orion.presence import (
    ActivityLog,
    InvalidWindow,
    PresencePolicy,
    PresenceRule,
    PresenceRuleStore,
    parse_window,
)

TZ = ZoneInfo("America/Sao_Paulo")
DAY = date(2026, 11, 9)  # segunda-feira


def at(h: int, m: int = 0, day: date = DAY) -> datetime:
    return datetime(day.year, day.month, day.day, h, m, tzinfo=TZ)


class FakeActivity:
    def __init__(self, first: datetime | None = None) -> None:
        self.first = first

    def first_activity_on(self, day: date) -> datetime | None:
        return self.first if self.first and self.first.date() == day else None

    def last_activity(self) -> datetime | None:
        return self.first


def msg(**kw: object) -> OutgoingMessage:
    return OutgoingMessage(title="t", **kw)  # type: ignore[arg-type]


def policy(rules: list[PresenceRule], first: datetime | None = None) -> PresencePolicy:
    return PresencePolicy(lambda: rules, FakeActivity(first), tz=TZ)


# --- gramática ---------------------------------------------------------------


def test_range_and_wraparound() -> None:
    act = FakeActivity()
    w = parse_window("22:00-07:00")
    assert w.contains(at(23), act) and w.contains(at(3), act)
    assert not w.contains(at(7), act) and not w.contains(at(12), act)
    d = parse_window("09:00-10:00")
    assert d.contains(at(9), act) and not d.contains(at(10), act)
    assert d.point() is None


def test_relative_windows() -> None:
    w = parse_window("until_first_activity")
    assert w.contains(at(10), FakeActivity())
    act = FakeActivity(at(8, 30))
    assert w.contains(at(8), act) and not w.contains(at(9), act)

    r = parse_window("first_activity+90m")
    assert r.contains(at(9, 59), act) and not r.contains(at(10), act)
    assert r.contains(at(23), FakeActivity())
    assert not parse_window("first_activity+2h").contains(at(10, 30), act)
    # atividade registrada em UTC é convertida ao fuso local
    utc = FakeActivity(at(8, 30).astimezone(ZoneInfo("UTC")))
    assert not parse_window("first_activity+30m").contains(at(9), utc)

    s = parse_window("06:00-first_activity+30m")
    assert not s.contains(at(5), FakeActivity())
    assert s.contains(at(7), FakeActivity())
    assert s.contains(at(8, 59), act) and not s.contains(at(9), act)


def test_point_window() -> None:
    w = parse_window("daily@08:00")
    assert w.point() == time(8, 0)
    assert not w.contains(at(8), FakeActivity())


@pytest.mark.parametrize(
    "bad",
    ["", "abc", "25:00-07:00", "08:00-08:00", "first_activity+0m", "daily@7", "first_activity+5d"],
)
def test_invalid_window(bad: str) -> None:
    with pytest.raises(InvalidWindow, match="[Jj]anela|deslocamento"):
        parse_window(bad)


# --- store -------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> Iterator[PresenceRuleStore]:
    facts = FactsStore(tmp_path / "facts.db")
    facts.initialize()
    yield PresenceRuleStore(facts)
    facts.close()


def test_store_round_trip(store: PresenceRuleStore) -> None:
    rule = PresenceRule(kind="quiet_window", window="until_first_activity", description="manhã")
    proposed = store.propose(rule)
    assert proposed.key == "presence.quiet_window.until-first-activity"
    assert store.list_active() == []
    assert [r.key for r in store.proposals()] == [proposed.key]

    confirmed = store.confirm(proposed)
    active = store.list_active()
    assert [r.key for r in active] == [confirmed.key]
    assert active[0].description == "manhã" and store.proposals() == []

    with pytest.raises(FactPoisoningAttempt):
        store.propose(rule)

    assert store.remove(confirmed.key) is True
    assert store.list_active() == []
    assert store.remove("outra.coisa") is False


def test_store_validation_and_unparsable(store: PresenceRuleStore, tmp_path: Path) -> None:
    with pytest.raises(InvalidWindow):
        store.confirm(PresenceRule(kind="digest", window="nope"))
    with pytest.raises(ValueError, match="Dias"):
        store.confirm(PresenceRule(kind="digest", window="daily@08:00", days=[7]))
    with pytest.raises(ValueError, match="presence"):
        store.confirm(PresenceRule(key="x.y", kind="digest", window="daily@08:00"))
    explicit = store.confirm(PresenceRule(key="presence.digest.manha", kind="digest", window="daily@08:00"))
    assert explicit.key == "presence.digest.manha"

    # fatos corrompidos e fora do prefixo são ignorados
    from orion.memory.models import FactCategory, FactEntry, FactStatus

    facts = store._facts
    for key, value in [
        ("presence.digest.lixo", "não é json"),
        ("presence.digest.janela", json.dumps({"kind": "digest", "window": "zzz"})),
        ("outra.pref", "{}"),
    ]:
        facts.upsert(
            FactEntry(
                key=key,
                value=value,
                category=FactCategory.USER_PREFERENCE,
                status=FactStatus.CONFIRMED,
            )
        )
    assert [r.key for r in store.list_active()] == ["presence.digest.manha"]


# --- política ----------------------------------------------------------------

QUIET = PresenceRule(
    key="presence.quiet_window.manha", kind="quiet_window", window="first_activity+30m"
)


def test_no_rules_default() -> None:
    p = policy([])
    assert p.decide(msg(), at(3)) == DEFAULT_DELIVERY
    assert not p.quiet_now(at(3))


def test_quiet_morning_acceptance() -> None:
    first = at(8, 0)
    p = policy([QUIET], first)
    inside = at(8, 10)
    assert p.quiet_now(inside)

    normal = p.decide(msg(), inside)
    assert normal.silent and normal.digest
    assert normal.channel_cap == "inbox" and normal.rule_key == QUIET.key
    assert normal.reason.startswith("Presença")
    assert p.decide(msg(priority="high"), inside).digest

    crit = p.decide(msg(priority="critical"), inside)
    assert crit.channel_cap == "notify" and not crit.silent and not crit.digest

    appr = p.decide(msg(kind="approval"), inside)
    assert appr.channel_cap == "notify" and appr.silent and not appr.digest

    # resumo/briefing não voltam para o resumo
    assert not p.decide(msg(kind="digest"), inside).digest

    after = at(8, 31)
    assert p.decide(msg(), after) == DEFAULT_DELIVERY
    assert not p.quiet_now(after)


def test_allow_critical_false() -> None:
    rule = QUIET.model_copy(update={"allow_critical": False})
    p = policy([rule], at(8))
    for m in (msg(priority="critical"), msg(kind="approval")):
        d = p.decide(m, at(8, 5))
        assert d.silent and d.digest and d.channel_cap == "inbox"


def test_channel_cap_combination() -> None:
    cap_notify = PresenceRule(
        key="presence.channel_cap.a", kind="channel_cap", window="09:00-18:00", channel_cap="notify"
    )
    cap_inbox = PresenceRule(
        key="presence.channel_cap.b", kind="channel_cap", window="10:00-12:00", channel_cap="inbox"
    )
    p = policy([cap_notify, cap_inbox])
    d = p.decide(msg(), at(9, 30))
    assert d.channel_cap == "notify" and not d.digest and not d.silent
    assert d.rule_key == cap_notify.key
    d2 = p.decide(msg(), at(11))
    assert d2.channel_cap == "inbox" and d2.rule_key == cap_inbox.key
    assert p.decide(msg(), at(20)) == DEFAULT_DELIVERY


def test_quiet_and_cap_combined_most_restrictive() -> None:
    cap_none = PresenceRule(
        key="presence.channel_cap.n", kind="channel_cap", window="00:00-23:59", channel_cap="none"
    )
    p = policy([QUIET, cap_none], at(8))
    d = p.decide(msg(priority="critical"), at(8, 5))
    assert d.channel_cap == "none" and d.rule_key == cap_none.key


def test_digest_rule_and_inert_rules() -> None:
    dig = PresenceRule(key="presence.digest.m", kind="digest", window="daily@08:00")
    p = policy([dig])
    d = p.decide(msg(priority="low"), at(15))
    assert d.digest and d.rule_key == dig.key and d.channel_cap == "inbox"
    inert = p.decide(msg(priority="critical"), at(15))
    assert not inert.digest and inert.channel_cap == "voice"
    assert not p.decide(msg(kind="approval"), at(15)).digest
    # briefing com horário fixo não afeta decisões
    brief = PresenceRule(key="presence.briefing.m", kind="briefing", window="daily@07:00")
    assert policy([brief]).decide(msg(), at(8)).reason != ""
    assert policy([brief]).decide(msg(), at(8)).silent is False


def test_days_filter() -> None:
    rule = QUIET.model_copy(update={"days": [0]})  # segunda
    p = policy([rule], at(8))
    assert p.decide(msg(), at(8, 5)).digest
    tuesday = date(2026, 11, 10)
    p2 = PresencePolicy(lambda: [rule], FakeActivity(at(8, day=tuesday)), tz=TZ)
    assert p2.decide(msg(), at(8, 5, tuesday)) == DEFAULT_DELIVERY


def test_naive_and_foreign_tz_now() -> None:
    p = policy([QUIET], at(8))
    assert p.decide(msg(), datetime(2026, 11, 9, 8, 5)).digest
    utc_now = at(8, 5).astimezone(ZoneInfo("UTC"))
    assert p.decide(msg(), utc_now).digest
    naive = PresencePolicy(lambda: [QUIET], FakeActivity(), tz=None)
    assert naive.quiet_now(datetime(2026, 11, 9, 8, 5))


def test_due_briefings() -> None:
    brief = PresenceRule(key="presence.briefing.m", kind="briefing", window="daily@07:00")
    dig = PresenceRule(key="presence.digest.t", kind="digest", window="daily@18:00", days=[0])
    other = PresenceRule(key="presence.quiet_window.x", kind="quiet_window", window="22:00-07:00")
    p = policy([brief, dig, other])
    assert p.due_briefings(at(6), {}) == []
    assert [r.key for r in p.due_briefings(at(7, 1), {})] == [brief.key]
    assert [r.key for r in p.due_briefings(at(19), {brief.key: DAY})] == [dig.key]
    assert p.due_briefings(at(19), {brief.key: DAY, dig.key: DAY}) == []
    tuesday = date(2026, 11, 10)
    assert [r.key for r in p.due_briefings(at(19, day=tuesday), {})] == [brief.key]


def test_policy_does_not_import_gateway() -> None:
    import orion.presence.policy as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "orion.gateway" not in src


# --- ActivityLog -------------------------------------------------------------


def test_activity_log_persistence(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "activity.json"
    log = ActivityLog(path, clock=lambda: at(9))
    assert log.first_activity_on(DAY) is None and log.last_activity() is None
    log.record()
    log.record(at(15))
    log.record(at(7))
    assert log.first_activity_on(DAY) == at(7)
    assert log.last_activity() == at(15)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    again = ActivityLog(path)
    assert again.first_activity_on(DAY) == at(7) and again.last_activity() == at(15)
    again.record(datetime(2026, 11, 9, 20, 0))  # ingênuo vira local
    assert again.last_activity() is not None


def test_activity_log_pruning_and_corrupt(tmp_path: Path) -> None:
    path = tmp_path / "a.json"
    log = ActivityLog(path)
    for i in range(1, 36):
        log.record(at(8, day=date.fromordinal(date(2026, 9, 1).toordinal() + i)))
    data = json.loads(path.read_text())
    assert len(data["days"]) == 30
    assert min(data["days"]) == date.fromordinal(date(2026, 9, 1).toordinal() + 6).isoformat()

    path.write_text("{ruim")
    assert ActivityLog(path).last_activity() is None
