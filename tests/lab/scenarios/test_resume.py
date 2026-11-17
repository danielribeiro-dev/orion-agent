"""v0.5.3 Sprint 3 — ``/resume`` por nome e data, em árvore (ADR-051, CA-13).

As sessões são semeadas antes do boot no ``~/.orion`` temporário do lab (índice + JSONL),
com datas relativas ao dia real: ``ontem`` e o mês corrente (``nov`` em novembro).
"""

from __future__ import annotations

import time as _time
from datetime import datetime, time, timedelta
from pathlib import Path

from orion.gateway.models import LLMMessage, MessageRole
from orion.sessions import TranscriptEntry
from orion.sessions.clock import local_day, local_now
from orion.sessions.index import SessionIndex

_ABBR = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
_NAMES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)


def _seed(orion_home: Path) -> tuple[datetime, datetime]:
    today = local_day(local_now(), time(4, 0))
    yesterday = datetime.combine(today - timedelta(days=1), time(15, 0)).astimezone()
    older = datetime.combine(today.replace(day=1) - timedelta(days=40), time(15, 0)).astimezone()
    index = SessionIndex(orion_home / "sessions.db")
    sessions = (
        ("lab-ontem-0001", "Plano da voz", yesterday, "planejar a voz"),
        ("lab-velha-0002", "Auditoria antiga", older, "auditar o PEP"),
    )
    for session_id, title, moment, text in sessions:
        iso = moment.isoformat()
        path = orion_home / "sessions" / "lab-ws" / f"{session_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            TranscriptEntry.of_meta(session_id=session_id, workspace="/tmp/lab").model_copy(update={"index": 0, "ts": iso}),
            TranscriptEntry.of_message(LLMMessage(role=MessageRole.USER, content=text)).model_copy(update={"index": 1, "ts": iso}),
            TranscriptEntry.of_message(LLMMessage(role=MessageRole.ASSISTANT, content=f"ok: {text}")).model_copy(update={"index": 2, "ts": iso}),
        ]
        path.write_text("".join(e.model_dump_json(exclude_none=True) + "\n" for e in lines), encoding="utf-8")
        index.register(session_id, "thread", title=title, workspace="/tmp/lab", created_at=iso, turn_count=1)
    index.close()
    return yesterday, older


def _type(lab, text: str) -> None:  # type: ignore[no-untyped-def]
    for char in text:
        lab.send(char)
        _time.sleep(0.05)


def _erase(lab, count: int) -> None:  # type: ignore[no-untyped-def]
    for _ in range(count):
        lab.key("backspace")
        _time.sleep(0.05)


def test_resume_filters_by_date_and_resumes_from_the_tree(open_lab, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    yesterday, _older = _seed(tmp_path / "home" / ".orion")
    lab = open_lab(fullscreen=True, rows=40)
    lab.submit("/resume")
    assert lab.wait_for("Retomar sessão", 20), lab.screen_text()
    screen = lab.screen_text()
    assert "Plano da voz" in screen and "Auditoria antiga" in screen, screen

    _type(lab, "ontem")
    assert lab.wait_for(r"Buscar: ontem", 10), lab.screen_text()
    screen = lab.screen_text()
    assert "Plano da voz" in screen and "Auditoria antiga" not in screen, screen
    assert f"{yesterday:%d/%m}" in screen and _NAMES[yesterday.month - 1] in screen, screen

    _erase(lab, len("ontem"))
    month = _ABBR[yesterday.month - 1]
    _type(lab, month)
    assert lab.wait_for(rf"Buscar: {month}", 10), lab.screen_text()
    screen = lab.screen_text()
    assert "Plano da voz" in screen and "Auditoria antiga" not in screen, screen
    assert str(yesterday.year) in screen, screen  # árvore ano › mês › dia

    lab.key("enter")
    assert lab.wait_for(r"Sessão 'Plano da voz' \(lab-onte\) retomada", 15, history=True), lab.history_text()[-2000:]
