"""A/B with a real LLM: ORION AgentSession with MCP starter pack OFF (A) vs ON (B).

Usage (from a project dir that has `.serena/project.yml`, see bench doc):
    OPENROUTER_API_KEY=... python scripts/ab_mcp_llm.py [--reps 2] [--model google/gemini-2.0-flash] [--dry]
Reads the key from $OPENROUTER_API_KEY or the file in $ORION_KEY_FILE. Never prints it.
Plan mode (read-only) is used so no file is modified; success is checked by substring ground truth.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from rich.console import Console

from orion.core.events import ActionEmitted
from orion.gateway.models import LLMResponseChunk
from orion.tui.session import AgentMode, AgentSession
from orion.tui.status_bar import SessionStatusBar

WS = Path.cwd()


def grep(pattern: str) -> str:
    return subprocess.run(["grep", "-rn", pattern, "src"], capture_output=True, text=True, cwd=WS).stdout


# (id, prompt, [must-contain groups: each group is a list of alternatives, any one satisfies])
TASKS = [
    ("T1", "Em qual arquivo e em qual linha começa o método PolicyEnforcementPoint.evaluate? Responda curto.",
     [["governance/pep.py"], ["185", "186"]]),
    ("T2", "Liste os métodos públicos (sem underscore) da classe MCPClient em src/orion/mcp/client.py. Responda só os nomes.",
     [["start"], ["connect"], ["disconnect"], ["close"], ["set_enabled"], ["ping"], ["call_tool"], ["all_tools"]]),
    ("T3", "Quais funções ou métodos em src/ chamam tool_action_level? Cite função e arquivo.",
     [["pep.py"], ["_effective_level"]]),
    ("T4", "Qual mensagem MCPClient.call_tool retorna quando o servidor excede o timeout? Cite o texto.",
     [["timed out after"]]),
]


def dry_provider(_spec):
    class P:
        async def stream(self, request):
            yield LLMResponseChunk(delta="resposta simulada governance/pep.py 185", is_final=True)
    return P()


def retrying_provider(spec):
    """Real provider wrapped with backoff on 429 (free tier), only before the first chunk."""
    from orion.gateway.providers.openrouter import OpenRouterProvider, ProviderAPIError, RateLimitError

    inner = OpenRouterProvider(api_key=os.environ.get("OPENROUTER_API_KEY", ""))

    class P:
        async def stream(self, request):
            for attempt in range(6):
                started = False
                try:
                    async for chunk in inner.stream(request):
                        started = True
                        yield chunk
                    return
                except (RateLimitError, ProviderAPIError):
                    if started or attempt == 5:
                        raise
                    await asyncio.sleep(10 * (attempt + 1))

    return P()


async def run_arm(arm: str, prompt: str, model: str, dry: bool) -> dict:
    home = Path(tempfile.mkdtemp(prefix=f"orion_ab_{arm}_"))
    console = Console(file=io.StringIO(), width=120)
    session = AgentSession(
        status_bar=SessionStatusBar(), console=console, workspace=WS, home=home,
        provider_factory=dry_provider if dry else retrying_provider, max_turns=12,
    )
    if session.registry.get(model) is None:  # e.g. OpenRouter ':free' models
        from orion.gateway.models import ModelSpec, ProviderName

        session.registry._catalog[model] = ModelSpec(
            id=model, name=model, provider=ProviderName.OPENROUTER, context_window=128_000,
            cost_input_m=0.0, cost_output_m=0.0,
        )
    session.set_model(model)
    session.set_mode(AgentMode.PLAN)
    session.budget.update_budget(2.0)
    tools: list[str] = []

    async def on_action(ev: ActionEmitted) -> None:
        tools.append(ev.tool)

    session.bus.subscribe(ActionEmitted)(on_action)
    if arm == "B":
        session.start_mcp()
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and any(s.status == "connecting" for s in session.mcp.servers.values()):
            await asyncio.sleep(0.5)
    t0 = time.monotonic()
    answer = await session.run_turn(prompt) or ""
    elapsed = time.monotonic() - t0
    if session.mcp is not None:
        await session.mcp.close()
    return {
        "answer": answer, "tools": tools, "tokens_in": session.tokens_in, "tokens_out": session.tokens_out,
        "cost": session.cost_total, "secs": elapsed,
        "mcp_calls": sum(1 for t in tools if t.startswith("mcp__")),
    }


def score(answer: str, groups: list[list[str]]) -> float:
    low = answer.lower()
    return sum(any(a.lower() in low for a in g) for g in groups) / len(groups)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--model", default="google/gemini-2.0-flash")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--tasks", default="")
    args = ap.parse_args()
    if not os.environ.get("OPENROUTER_API_KEY") and os.environ.get("ORION_KEY_FILE"):
        os.environ["OPENROUTER_API_KEY"] = Path(os.environ["ORION_KEY_FILE"]).read_text().strip()
    if not args.dry and not os.environ.get("OPENROUTER_API_KEY"):
        sys.exit("OPENROUTER_API_KEY (or ORION_KEY_FILE) required")
    results = []
    only = set(filter(None, args.tasks.split(",")))
    for tid, prompt, groups in [t for t in TASKS if not only or t[0] in only]:
        for arm in ("A", "B"):
            for rep in range(args.reps):
                r = await run_arm(arm, prompt, args.model, args.dry)
                r.update(task=tid, arm=arm, rep=rep, score=score(r["answer"], groups))
                results.append(r)
                print(f"{tid} {arm}#{rep} in={r['tokens_in']} out={r['tokens_out']} ${r['cost']:.4f} "
                      f"tools={len(r['tools'])} mcp={r['mcp_calls']} score={r['score']:.2f} {r['secs']:.1f}s", flush=True)
    print("\n== resumo (média por tarefa/braço) ==")
    print(f"{'tarefa':6}{'braço':6}{'tok_in':>9}{'tok_out':>9}{'custo$':>9}{'tools':>7}{'mcp':>5}{'acerto':>8}")
    for tid in dict.fromkeys(r["task"] for r in results):
        for arm in ("A", "B"):
            rs = [r for r in results if r["task"] == tid and r["arm"] == arm]
            m = lambda k: statistics.mean(r[k] if k != "tools" else len(r[k]) for r in rs)  # noqa: E731
            print(f"{tid:6}{arm:6}{m('tokens_in'):>9.0f}{m('tokens_out'):>9.0f}{m('cost'):>9.4f}{m('tools'):>7.1f}{m('mcp_calls'):>5.1f}{m('score'):>8.2f}")
    for arm in ("A", "B"):
        rs = [r for r in results if r["arm"] == arm]
        print(f"TOTAL {arm}: in={sum(r['tokens_in'] for r in rs)} out={sum(r['tokens_out'] for r in rs)} "
              f"${sum(r['cost'] for r in rs):.4f} acerto={statistics.mean(r['score'] for r in rs):.2f}")
    out = Path(os.environ.get("AB_OUT", "ab_results.json"))
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print("salvo em", out)


if __name__ == "__main__":
    asyncio.run(main())
