"""Turno REAL com a Anthropic (CA-01). Opt-in: ORION_LIVE=1 pytest -m live. Gasta tokens."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from orion.gateway.budget import BudgetGuard
from orion.gateway.credentials import load_anthropic_key
from orion.gateway.ledger import CostLedger
from orion.gateway.models import LLMMessage, LLMRequest, MessageRole
from orion.gateway.providers.anthropic import AnthropicProvider

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("ORION_LIVE") != "1", reason="defina ORION_LIVE=1"),
]


async def test_live_turn_streams_and_records_usage(tmp_path: Path) -> None:
    key = load_anthropic_key(Path.home() / ".orion")
    if not key:
        pytest.skip("sem ANTHROPIC_API_KEY")
    ledger = CostLedger(db_path=tmp_path / "m.db")
    BudgetGuard(ledger=ledger).check(is_local_model=False)  # respeita o teto

    request = LLMRequest(
        model="claude-haiku-5-5",  # o mais barato
        max_tokens=64,
        messages=[LLMMessage(role=MessageRole.USER, content="Responda apenas: pong")],
    )
    provider = AnthropicProvider(api_key=key)
    chunks = [c async for c in provider.stream(request)]
    text = "".join(c.delta for c in chunks)
    usage = chunks[-1].usage
    assert text and usage and usage.prompt_tokens > 0 and usage.completion_tokens > 0
    rec = ledger.record_turn_cost("anthropic", "claude-haiku-5-5", usage)
    assert rec.cost_usd > 0
