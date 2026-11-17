"""Horizon em movimento (Sprint 2): larguras sem corte (CA-07), golden do logo, prompt logo abaixo
do banner (V-02) e réguas que seguem o texto em multilinha (F-07/F-08)."""

from __future__ import annotations

from pathlib import Path

import pytest

GOLDEN = Path(__file__).resolve().parents[3] / "docs" / "design" / "horizon" / "splash-110.txt"


def _rows(lab) -> list[str]:  # type: ignore[no-untyped-def]
    return [line.rstrip() for line in lab.screen.display]


@pytest.mark.parametrize(
    ("cols", "must", "must_not"),
    [(110, "Alt+T esforço", ""), (80, "Ctrl+C ×2 sai", "Alt+T"), (60, "@ arquivos", "Ctrl+C")],
)
def test_widths_hint_fits_and_prompt_follows_banner(open_lab, cols, must, must_not) -> None:  # type: ignore[no-untyped-def]
    lab = open_lab(cols=cols)
    rows = _rows(lab)
    hint = next(i for i, row in enumerate(rows) if "/ comandos" in row)
    assert must in rows[hint], rows[hint]
    if must_not:
        assert must_not not in rows[hint]
    rule = next(i for i, row in enumerate(rows) if row and set(row) == {"─"})
    assert 1 <= rule - hint <= 2, "\n".join(rows)  # sem o vão do dock (V-02)
    assert rows[rule + 1].startswith("❯") and rows[rule + 3].startswith(("auto ·", "claude"))


def test_logo_matches_golden(open_lab) -> None:  # type: ignore[no-untyped-def]
    lab = open_lab(cols=110)
    golden = [line[:41] for line in GOLDEN.read_text(encoding="utf-8").splitlines()[1:7]]
    rows = _rows(lab)
    start = next(i for i, row in enumerate(rows) if "██████╗" in row)
    assert [row[:41] for row in rows[start : start + 6]] == golden
    assert "O.R.I.O.N" in rows[start + 1] and "Operational Reasoning" in rows[start + 2]


def test_rules_follow_multiline_input(open_lab) -> None:  # type: ignore[no-untyped-def]
    lab = open_lab()
    lab.send("linha um")
    lab.send("\x1b\r")  # Alt+Enter
    lab.send("linha dois")
    lab.pump(0.8)
    rows = _rows(lab)
    i = next(n for n, row in enumerate(rows) if row.startswith("❯ linha um"))
    assert "linha dois" in rows[i + 1] and set(rows[i + 2]) == {"─"}, "\n".join(rows[i - 2 : i + 4])
    lab.send("\x7f" * len("linha dois") + "\x7f")  # apaga a segunda linha e a quebra
    lab.pump(0.8)
    rows = _rows(lab)
    i = next(n for n, row in enumerate(rows) if row.startswith("❯ linha um"))
    assert set(rows[i + 1]) == {"─"}, "\n".join(rows[i - 2 : i + 4])  # régua segue o texto
    assert rows[i + 2].startswith("auto ·")
