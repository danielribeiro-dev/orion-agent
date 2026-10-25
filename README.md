<div align="center">

                                              
                                                ██████╗ ██████╗ ██╗ ██████╗ ███╗   ██╗
                                               ██╔═══██╗██╔══██╗██║██╔═══██╗████╗  ██║
                                               ██║   ██║██████╔╝██║██║   ██║██╔██╗ ██║
                                               ██║   ██║██╔══██╗██║██║   ██║██║╚██╗██║
                                               ╚██████╔╝██║  ██║██║╚██████╔╝██║ ╚████║
                                                ╚═════╝ ╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═╝  ╚═══╝
                                              

### **O.R.I.O.N — Operational Reasoning & Intelligence Orchestration Network**
*The Sovereign, Event-Driven Personal Intelligence & Agentic Operating System.*

*Inspired by the vision of J.A.R.V.I.S. — engineered for the real world as an open, sovereign, extensible, and enterprise-grade autonomous platform.*

<br/>

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Linux-FCC624.svg?style=flat-square&logo=linux&logoColor=black)](https://kernel.org)
[![Version](https://img.shields.io/badge/Version-v0.1.0_Stable-00C7B7?style=flat-square)]()
[![Tests](https://img.shields.io/badge/Tests-210%20passing-brightgreen?style=flat-square)]()
[![Coverage](https://img.shields.io/badge/Coverage-92.57%25-brightgreen?style=flat-square)]()
[![MCP Native](https://img.shields.io/badge/MCP-Native_Client-8A2BE2?style=flat-square)]()

<br/>

[Quickstart](#-quickstart-in-30-seconds) • [Terminal In Action](#-terminal-in-action) • [Why O.R.I.O.N?](#-why-orion) • [Core Architecture](#-core-architecture) • [Roadmap](#-evolution-roadmap) • [Author & License](#-author--license)

</div>

---

## ⚡ Terminal in Action

```text
$ orion "Refactor our auth middleware to support Ed25519 signatures and run tests"

╭─ O.R.I.O.N ────────────────────────────────────────────────────────────────────────╮
│ 🧠 Cognitive Loop Initiated · Turn 1/25 · Governance: PEP Supervised (Level 2)      │
│ 🔎 Searching codebase for cryptographic utilities...                               │
│ ⚡ tool_call: search_files(pattern="*auth*") -> 2 matches found                     │
│ 📖 tool_call: read_file(path="src/orion/core/auth.py", lines=[1, 60])               │
│ ✍️  tool_call: edit_file(path="src/orion/core/auth.py", target=..., replacement=...) │
│ 🧪 tool_call: run_command("pytest tests/unit/test_auth.py -v")                      │
│    └─ 12 passed in 0.04s ✅                                                        │
│ 📊 Turn Financial Ledger: $0.0031 USD · Tokens: 1,840 in / 420 out                  │
╰────────────────────────────────────────────────────────────────────────────────────╯
```

---

## 🌟 Why O.R.I.O.N?

Most AI agents today are either fragile toy scripts or opaque cloud silos that lock you into proprietary ecosystems. **O.R.I.O.N** is built from first principles as an **autonomous, sovereign personal engineering copilot and operating companion**.

It combines the battle-tested paradigms of modern agentic engineering:

- 🔄 **Event-Sourced Cognitive Stream (Inspired by OpenHands):** An immutable, asynchronous Action-Observation event stream. Every decision, tool invocation, and environment feedback is recorded into an append-only audit ledger.
- 🗡️ **5 Surgical Native Primitive Tools (Inspired by Claude Code):** Zero bloat or fragile wrappers. The agent interacts with your system through 5 canonical primitives: `run_command`, `read_file`, `write_file`, `edit_file` (exact block replacement), and `search_files`.
- 🧠 **Continuous Triple Memory (Semantic + Exact + Episodic):**
  - **Exact Timeline Search:** SQLite FTS5 with BM25 full-text ranking.
  - **Conceptual Retrieval:** Local, private, offline vector inference via FastEmbed + ONNX.
  - **Structured Typed Facts:** Cryptographically shielded decision stores with anti-poisoning `CONFIRMED` / `DEPRECATED` status.
- 🛡️ **Hardened Governance & Nuclear Safety (PEP):** Built on a strict **"Deny by Default"** security model. Destructive filesystem operations, sensitive credential access, and high-risk terminal commands are intercepted and audited by the Policy Enforcement Point (PEP).
- 🔌 **Universal Extensibility via MCP:** Native client for the [Model Context Protocol (MCP)](https://modelcontextprotocol.io), seamlessly integrating external tools, databases, and services without proprietary code locks.
- 💸 **Smart Model Routing & Real-Time Token Ledger:** Autonomous switching between deep-reasoning models (Claude Opus/Sonnet) and rapid-execution engines (Gemini Flash/Qwen Coder) with exact per-token cost ledgering in USD/BRL.

---

## 🏛️ Core Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           TUI / Stream CLI Interface                            │
│           (Rich / Prompt-Toolkit: Streaming Tokens, Diffs, Slash Commands)      │
└────────────────────────────────────────┬────────────────────────────────────────┘
                                         │
┌────────────────────────────────────────▼────────────────────────────────────────┐
│                     Action-Observation Event Stream (AOS)                       │
│        (ReAct Cognitive Loop, Turn Budgeting, Replayable Append-Only Ledger)    │
├────────────────────────────────────────┬────────────────────────────────────────┤
│           Triple Memory Engine         │            Execution Engine            │
│  • Timeline & SQLite FTS5 (BM25)       │  • PEP (Policy Enforcement Point)      │
│  • FastEmbed + ONNX Local Embeddings   │  • Native LocalRuntimeProvider         │
│  • Structured Facts & Decisions Store  │  • 5 Surgical Primitive Native Tools   │
│  • Progressive Context Unpacking       │  • Native MCP Client & Multi-Channels  │
└────────────────────────────────────────┴────────────────────────────────────────┘
```

---

## 🚀 Quickstart in 30 Seconds

### Prerequisites

- **Python 3.11+**
- **Linux** (tested on Ubuntu 22.04+, Debian, Arch) / macOS

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/danielribeiro-dev/orion-agent.git
cd orion-agent

# Set up virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in editable mode with development dependencies
pip install -e ".[dev]"
```

> **Tip:** You can also use [`uv`](https://github.com/astral-sh/uv) for lightning-fast installation:
> ```bash
> uv venv && source .venv/bin/activate && uv pip install -e ".[dev]"
> ```

### 2. Verify Installation

```bash
orion --version
# Output: O.R.I.O.N v0.1.0-alpha

orion info
# Displays system status, active providers, and memory statistics
```

---

## 🧪 Rigorous Quality & Test Suite

O.R.I.O.N enforces strict testing standards. Zero merges occur without comprehensive unit, integration, and security verification.

```bash
# Run the complete test suite
pytest tests/

# Run with missing line coverage report
pytest --cov=src/orion --cov-report=term-missing tests/

# Run security & PEP audit tests exclusively
pytest tests/e2e/test_security_audit.py -v
```

```text
============================== 210 passed in 0.48s ==============================
Coverage: 92.57% (Enforced threshold: >= 85.00%) ✅
Status: Clean / Production Grade
```

---

## 🗺️ Evolution Roadmap

The system is developed under a formal **Doc-First Engineering** methodology, where every version and sprint is specified before implementation.

| Version | Status | Milestone Focus |
| :--- | :---: | :--- |
| **`v0.1.0`** | ✅ **STABLE** | **Clean Foundation & Core ReAct Engine** (210 tests · 92.57% coverage · 5 primitives · PEP) |
| **`v0.2.0`** | 🔄 *In Progress* | **Cognitive Continuity:** Triple Memory (SQLite FTS5 + FastEmbed ONNX), Agent Skills (`SKILL.md`), and Dynamic Compaction |
| **`v0.3.0`** | 📋 *Planned* | **Model Gateway & Financial Ledger:** Real-time token accounting, autonomous routing, and offline resilience heartbeat |
| **`v0.4.0`** | 📋 *Planned* | **High-Performance Stream TUI/CLI:** Slash commands (`/plan`, `/compact`), interactive diff inspector, and native MCP client |
| **`v0.5.0`** | 📋 *Planned* | **Ambient Voice & Headless Daemon:** Background systemd service, local wake word, and real-time audio interaction |
| **`v1.0.0`** | 🎯 *Target* | **General Production Release:** Autonomous sovereign personal operating intelligence |

Full architecture specifications and sprint schedules are available in [`docs/planning/`](docs/planning/).

---

## 🛡️ Principles & Philosophy

1. **Deny by Default:** No destructive or modifying action is executed without validation through the Policy Enforcement Point (PEP).
2. **Deterministic Verification:** Attempt $\ne$ Done. A task is only marked as finished when concrete evidence has been verified.
3. **Memory is More than Vectors:** Contextual intelligence requires chronological timeline truth and verified facts, not just probabilistic cosine proximity.
4. **Sovereign & Anti-Lock-in:** No proprietary cloud vendor tools are hardcoded into the kernel. All extensions adhere to open standards (MCP, Python protocols).

---

## 👨‍💻 Author & License

Developed with passion by **Daniel Ribeiro** ([@danielribeiro-dev](https://github.com/danielribeiro-dev)).  
*Backend Developer @ Talk Code — Software House & AI Systems Architect.*

Distributed under the **Apache License 2.0**. See [`LICENSE`](LICENSE) for details.
