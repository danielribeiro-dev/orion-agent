<div align="center">

```
  ██████╗ ██████╗ ██╗ ██████╗ ███╗   ██╗
 ██╔═══██╗██╔══██╗██║██╔═══██╗████╗  ██║
 ██║   ██║██████╔╝██║██║   ██║██╔██╗ ██║
 ██║   ██║██╔══██╗██║██║   ██║██║╚██╗██║
 ╚██████╔╝██║  ██║██║╚██████╔╝██║ ╚████║
  ╚═════╝ ╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═╝  ╚═══╝
```

### **O.R.I.O.N — Operational Reasoning & Intelligence Orchestration Network**
*A sovereign, event-driven personal engineering agent that lives in your terminal.*

*Inspired by J.A.R.V.I.S. — built as an open, auditable, token-frugal agent you own end to end.*

<br/>

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Linux-FCC624.svg?style=flat-square&logo=linux&logoColor=black)](https://kernel.org)
[![Version](https://img.shields.io/badge/Version-v0.5.2--alpha-00C7B7?style=flat-square)]()
[![Tests](https://img.shields.io/badge/Tests-2123%20passing-brightgreen?style=flat-square)]()
[![Coverage](https://img.shields.io/badge/Coverage-93.6%25-brightgreen?style=flat-square)]()
[![MCP Native](https://img.shields.io/badge/MCP-Native_Client-8A2BE2?style=flat-square)]()

<br/>

[Terminal In Action](#-terminal-in-action) • [Why O.R.I.O.N?](#-why-orion) • [Quickstart](#-quickstart) • [Using the TUI](#-using-the-tui) • [Architecture](#-core-architecture) • [Roadmap](#-evolution-roadmap) • [License](#-author--license)

</div>

---

## ⚡ Terminal in Action

O.R.I.O.N runs as a full-screen terminal app: the conversation scrolls above, the input stays pinned at the bottom and keeps accepting text while the agent thinks, writes or runs tools. Its interface uses a small fixed glyph set and no emoji.

```text
❯ fix the greeting in sample.py

▸ Reasoning · 4.1s · 1.2k tok   Alt+R opens
I'll read the file first.

✔ Read  sample.py  ·  0.0s
  › 6 lines
✔ Edit  sample.py  ·  0.1s
  › +1 −1
╭─ [PEP] Authorization required · action level 3 ──────────────────────────────────╮
│  Action     Run an operating-system command                                        │
│  Command    pytest -q tests/test_sample.py                                         │
╰────────────────────────────────────────────────────────────────────────────────────╯
✔ approved · action level 3
✔ Bash  pytest -q tests/test_sample.py  ·  1.4s  ·  exit 0
  │ 12 passed in 0.04s

Done. The greeting is now formal.

✔ 12.4s · 3 tools · 2.1k tok · US$ 0.0050
──────────────────────────────────────────────────────────────────────────────────────
❯ type your instruction…
──────────────────────────────────────────────────────────────────────────────────────
accept-edits · claude-sonnet-5-5 · 4% ctx · US$ 0.010 · PEP 2 · Ready ●
```

*(The interface ships in Brazilian Portuguese; this sample is translated. Reference screens: [`docs/design/bridge/`](docs/design/bridge/).)*

---

## 🌟 Why O.R.I.O.N?

- 🔄 **Event-sourced cognition.** An asynchronous Action-Observation stream drives a ReAct loop. Every decision, tool call and observation is recorded in an append-only audit log.
- 🛡️ **Deny by default (PEP).** Every mutating action goes through the Policy Enforcement Point. Destructive commands (and the agent updating its own installation) require OS step-up authentication that hooks, subagents, schedules or rules can never bypass.
- 🧠 **Memory that is more than vectors.** Five cognitive spheres: user profile, identity, environment, typed project decisions (`CONFIRMED` / `INFERRED` / `DEPRECATED`) and an episodic timeline with SQLite FTS5 (BM25), plus optional local embeddings (FastEmbed + ONNX) that are never downloaded without consent.
- 🤖 **Claude-grade agent loop.** Native Anthropic provider with structured, parallel tool use, prompt caching and extended thinking; OpenRouter and local Ollama fallback; sessions with resume and rewind; hooks, rules, custom slash commands, skills (`SKILL.md`), subagents with privilege ceilings, background tasks and an opt-in daemon with schedules that spends **zero tokens when idle**.
- 🔌 **MCP native.** Model Context Protocol client (stdio, SSE and HTTP with OAuth), with a PEP level per tool.
- 💸 **Real-time cost ledger.** Per-turn and per-session cost in USD/BRL, a daily `BudgetGuard`, and model routing by task complexity.
- 🖥️ **A TUI built for daily use.** Full-screen renderer with a live input and message queue, collapsible reasoning and tool output, searchable transcript, readable memory views, terminal-native signals (tab title, progress, focus) and a classic inline renderer as fallback.

---

## 🚀 Quickstart

### Prerequisites

- **Python 3.11+**
- **Linux** (developed on Ubuntu; GNOME Terminal, Ghostty, Kitty, WezTerm). macOS is untested.
- Optional: [`uv`](https://github.com/astral-sh/uv) for faster installs.

### 1. Install (no virtualenv activation needed)

```bash
git clone https://github.com/danielribeiro-dev/orion-agent.git
cd orion-agent

scripts/install.sh          # pinned install of this checkout
# or
scripts/install.sh --dev    # editable: the command follows the repository code
```

The installer creates `~/.local/share/orion/versions/<version>/` with its own virtualenv, points `current` at it and writes the `orion` and `orion-agent` launchers to `~/.local/bin`. Your data lives only in `~/.orion/`.

```bash
orion --version             # works in any terminal, no venv activation
orion update --check        # look for a newer tagged release
orion update                # install it side by side and switch atomically
orion update --rollback     # go back to the previous version
```

### 2. Add a provider key

Keys live in `~/.orion/.env` (created with `0600` permissions on first run; the agent itself can never read it):

```bash
ANTHROPIC_API_KEY=...       # recommended
OPENROUTER_API_KEY=...      # free and paid models via OpenRouter
```

Without a key, O.R.I.O.N can still use a local Ollama model.

### 3. Run

```bash
orion                       # full-screen TUI
orion --continue            # resume the latest session in this directory
ORION_TUI=classic orion     # classic inline renderer
orion daemon status         # opt-in background daemon (systemd --user)
```

### Development setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

---

## ⌨️ Using the TUI

| Key | Action |
| :--- | :--- |
| `Enter` | Send. While the agent is working, the message is **queued** and sent when the turn ends |
| `Esc` | Interrupt the current turn (text already shown is kept) |
| `↑` (empty input) | Take queued messages back for editing |
| `Alt+R` / `Alt+E` | Open or close the last reasoning block / tool output **in place** (or click it) |
| `Ctrl+O` | Full transcript with everything expanded: `/` search, `n`/`N` next, `[` dump to terminal scrollback, `q` back |
| `PgUp` / `PgDn`, mouse wheel | Scroll; `Ctrl+End` jumps back to the latest output |
| `Shift+Tab` / `Alt+T` | Cycle agent mode / reasoning effort |
| `Alt+Enter` | New line |
| `Ctrl+C` ×2 or `/exit` | Quit (a resume hint is left in your scrollback) |

Slash commands (`/` opens the menu): `/help`, `/model`, `/config`, `/context`, `/cost`, `/memory`, `/timeline`, `/recall`, `/resume`, `/rewind`, `/diff`, `/undo`, `/plan`, `/review`, `/agents`, `/tasks`, `/loop`, `/mcp`, `/skills`, `/daemon`, `/doctor`, `/tui` and more.

Environment switches: `ORION_TUI=classic|fullscreen`, `ORION_MOUSE=0` (native text selection), `ORION_SYNC_OUTPUT=0`, `ORION_PROGRESS=0`.

---

## 🏛️ Core Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    TUI: full-screen (prompt_toolkit) · classic (Rich)            │
│    transcript cells · live input & queue · PEP overlays · slash commands         │
└────────────────────────────────────────┬────────────────────────────────────────┘
                                         │ SessionSink (terminal · IPC · null)
┌────────────────────────────────────────▼────────────────────────────────────────┐
│                     Action-Observation Event Stream (ReAct)                      │
│         turn budgeting · auto-compaction · sessions · hooks · subagents          │
├──────────────────────────┬───────────────────────────┬──────────────────────────┤
│      Memory (5 spheres)  │     Model Gateway         │    Execution & Policy    │
│  • timeline + FTS5/BM25  │  • Anthropic · OpenRouter │  • PEP (deny by default) │
│  • typed facts           │  • Ollama fallback        │  • nuclear OS step-up    │
│  • local embeddings      │  • router · breaker       │  • native tools · MCP    │
│  • compact manifest      │  • cost ledger · budget   │  • audit log             │
├──────────────────────────┴───────────────────────────┴──────────────────────────┤
│        Daemon (opt-in): IPC · schedules · jobs · inbox · desktop/Telegram        │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🧪 Quality

Development is **Doc-First**: every version and sprint is specified (with ADRs) before code is written.

```bash
pytest tests/ --cov=src/orion --cov-report=term-missing   # 2123 tests, ~93.6% coverage (gate: 85%)
pytest -m lab tests/lab                                    # 25 real-PTY TUI scenarios with a scripted provider
pytest tests/e2e/test_security_audit.py -v                 # PEP and security audit
ruff check src tests && mypy src                           # lint + strict typing
```

No automated test ever calls a paid or free model provider; live runs are opt-in with `ORION_LIVE=1`.

---

## 🗺️ Evolution Roadmap

| Version | Status | Focus |
| :--- | :---: | :--- |
| **`v0.1.0`** | ✅ Stable | Clean foundation, ReAct engine, native tools, PEP |
| **`v0.2.0`** | ✅ Stable | Five-sphere memory, skills (`SKILL.md`), dynamic compaction |
| **`v0.3.0`** | ✅ Done | Model gateway, cost ledger, offline resilience, nuclear step-up |
| **`v0.4.0`** | ✅ Implemented | Streaming CLI, slash commands, diff viewer, native MCP client |
| **`v0.5.0`** | 🚀 In progress | Claude-grade agent: native Anthropic provider, tool use, sessions, hooks, full MCP, subagents, daemon |
| **`v0.5.1`** | ✅ Implemented | Horizon: visual identity and TUI stability, real-PTY test lab |
| **`v0.5.2`** | ✅ Implemented | Bridge: full-screen TUI, motion language, readable memory, install without venv, `orion update` |
| **`v0.5.3`** | 📋 Proposed | Living memory and a lean core (smaller base prompt, reliable memorization) |
| **`v0.6.0`** | 📋 Planned | Ambient mode and local voice on top of the daemon |
| **`v0.7.0`** | 📋 Planned | Dedicated desktop cockpit |
| **`v1.0.0`** | 🎯 Target | Production release |

Specifications, sprint plans and decisions: [`docs/planning/`](docs/planning/).

---

## 🛡️ Principles

1. **Deny by default.** Nothing mutates your system without passing the PEP.
2. **Verified, not attempted.** A task is done only when evidence confirms it.
3. **Memory is more than vectors.** Chronological truth and verified facts come first.
4. **Sovereign and frugal.** Open standards (MCP, Python protocols), local-first where possible, zero tokens when idle.

---

## 👨‍💻 Author & License

Developed with passion by **Daniel Ribeiro** ([@danielribeiro-dev](https://github.com/danielribeiro-dev)).  
*Backend Developer @ Talk Code — Software House & AI Systems Architect.*

Distributed under the **Apache License 2.0**. See [`LICENSE`](LICENSE).
