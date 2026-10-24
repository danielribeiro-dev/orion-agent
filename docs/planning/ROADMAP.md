# O.R.I.O.N — Master Evolution Roadmap
*(Operational Reasoning & Intelligence Orchestration Network)*

> **Visão Geral:** Este documento estabelece o roadmap estratégico, tecnológico e executivo do **O.R.I.O.N**, desde a fundação inicial do núcleo de orquestração até a consolidação da plataforma de inteligência pessoal de alta autonomia.  
> **Filosofia:** *Estável antes de ambicioso. Seguro antes de autônomo. Documentado antes de codificado.*

---

## 🧭 1. O Benchmark Estratégico: Superando o Mercado (2026)

O O.R.I.O.N foi projetado desde o dia zero para **superar estruturalmente** os agentes mais avançados do mercado (**Claude Code, Google Antigravity CLI, OpenHands, Aider e Hermes Agent**) nas 5 dimensões do seu próprio nome:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       O.R.I.O.N — O PACTO DO ACRÔNIMO                       │
├─────────────────────────────────────────────────────────────────────────────┤
│  O — Operational    │ Operações reais no SO com PEP determinístico (0 a 3) │
│  R — Reasoning      │ ReAct + Action-Observation Event Stream + Self-Healing│
│  I — Intelligence   │ Linha do Tempo Contínua + Memória Tríplice + Custos   │
│  O — Orchestration  │ Orquestrador Mestre + Artefatos + Subagentes + MCP    │
│  N — Network        │ Presença Ambiente Headless + Resiliência Offline      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Matriz Comparativa de Superioridade

| Dimensão | Claude Code | Antigravity CLI | OpenHands | Aider | **O.R.I.O.N (Nossa Meta)** |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Arquitetura Central** | Master Loop síncrono | Loop com Subagentes & MCP | Action-Observation Event Stream | Architect / Editor Loop | **Event Stream Assíncrono com Event Sourcing Imutável** |
| **Manipulação de Código** | `str_replace_editor` (Exact match) | `edit_file` cirúrgico + AST | Edições completas / patch | Unified Diff / Whole File | **Exact-Match Anchored Editor + Tree-sitter AST Fallback** |
| **Sistema de Habilidades (Skills)** | Instruções em `CLAUDE.md` / Commands | Padrão `SKILL.md` com Progressive Disclosure | Microagents (`.agents/skills/`) | Instruções no chat | **Universal Agent Skills Standard (`SKILL.md`) com Auto-Destilação (`/learn`)** |
| **Memória & Continuidade** | Auto-compaction pontual; sem histórico entre sessões | Memory MCP (Grafo de Conhecimento) | Histórico de eventos da sessão | Git commit history | **Linha do Tempo Contínua & Memória Tríplice (FTS5 + ONNX + Fatos) + RRF + Dynamic Compaction** |
| **Interface com Usuário** | Terminal CLI puro | Terminal + Artifacts estruturados | Web UI / Browser | Terminal CLI | **TUI Sob Demanda (Rich/Diffs) + Artifacts + Voz Headless (Boot Daemon)** |
| **Governança & Segurança** | Prompts de confirmação manuais | Modos supervisionado / autônomo | Sandbox de contêiner | Nenhuma (executa no host) | **Deterministic PEP (4 Níveis: 0 a 3) + Bubblewrap Sandboxing** |
| **Consciência de Custos** | Contagem bruta de tokens | Auditoria de tokens e cache | Nenhuma integrada | Estimativa no prompt | **Real-Time Cost Ledger (USD & BRL) + Model Gateway com Auto-Routing** |
| **Tolerância Offline** | Falha sem internet | Falha sem internet | Falha sem internet | Suporte parcial a Ollama | **ORION Imortal: Failover < 2s para LLM Local + Reconciliação sem Conflito** |

---

## 🗺️ 2. Mapa Completo de Versões do O.R.I.O.N

```text
v0.1.0  ── Clean Foundation & Core ReAct Engine ────────────────── [FASE ATUAL]
  │        (5 Ferramentas Nativas, Action-Observation, PEP e Artefatos)
v0.2.0  ── Cognitive Continuity: Triple Memory, Agent Skills Standard & Dynamic Compaction
  │        (SQLite WAL FTS5 + ONNX FastEmbed Local + Fatos RRF + SKILL.md Engine + Compactor)
v0.3.0  ── Model Gateway, Real-Time Cost Ledger & Offline Resilience
  │        (Auto-Routing por Complexidade, Token Ledger no CLI, ORION Imortal)
v0.4.0  ── Dynamic Interactive TUI, Slash Commands (/) & Native MCP
  │        (Rich Markdown Streaming, Tree-sitter Repo Map, MCP Client stdio/SSE)
v0.5.0  ── Ambient Mode & Headless Voice Pipeline
  │        (Systemd Boot Daemon, openWakeWord, Faster-Whisper, Piper TTS)
v1.0.0  ── Production Release: Autonomous Personal Operating Intelligence
  │        (Blindagem de Segurança Militar, Pacotes Binários e Multiplataforma)
v1.5.0  ── Self-Healing Engine, Bubblewrap Sandboxing & Dynamic Subagents
v2.0.0  ── Ghost Input (/dev/uinput), Chrome CDP Automation & Zero-Knowledge Vault
v2.5.0  ── Spatial Interaction & Hands-Free Burst Vision (Ray Casting & AT-SPI2)
v3.0.0  ── Full Ambient Symbiosis & Multi-Device Distributed Coordination
```

---

## 📋 3. Detalhamento da Versão Ativa (v0.1.0)

### 🚀 v0.1.0 — Clean Foundation & Core ReAct Engine
* **Status:** 🔄 Pronto para Iniciar Implementação  
* **Foco:** Base de código limpa em Python 3.11+, tipagem Pydantic v2, loop assíncrono ReAct baseado em **Action-Observation Event Stream**, delimitação estrita de prompts, 5 Ferramentas Primitivas Nativas de SO (sem dependência de muletas externas), governança determinística (PEP) e subsistema inicial de Artefatos.
* **Documentação:** [`docs/planning/versions/v0.1.0/VERSION.md`](versions/v0.1.0/VERSION.md)
* **Sprints:**
  - `sprint-1`: Setup do ambiente, `pyproject.toml`, CLI Skeleton (Rich/Typer), ASCII Banner e Tipagem Estrita
  - `sprint-2`: Core ReAct Engine, Action-Observation EventBus Assíncrono, Turn Budgeting e Subsistema de Artefatos
  - `sprint-3`: As 5 Ferramentas Primitivas Nativas (`run_command`, `read_file`, `write_file`, `edit_file`, `search_files`), LocalRuntimeProvider e PEP Governance (Níveis 0 a 3)
  - `sprint-4`: Bateria de Testes Automatizados E2E, Cobertura $\ge 85\%$, Auditoria de Segurança e Congelamento da v0.1.0

---

## 👥 4. Guia para Desenvolvedores e Contribuidores

1. **Entenda onde estamos:** Consulte o status da versão ativa em [`docs/planning/versions/`](versions/) e o backlog em `.claudex/progress.md`.
2. **Respeite o fluxo de Sprints:** Cada versão é dividida em sprints atômicas em `docs/planning/versions/<versao>/sprints/`. Cada sprint tem seu escopo estrito, contratos de código e critérios de aceite (Definition of Done).
3. **Padrão Doc-First:** Nenhuma linha de código em `src/` é escrita sem antes atualizar ou criar a especificação correspondente.
4. **Zero Código não Testado:** Qualquer alteração no Core ou Runtime deve ser acompanhada de testes automatizados com meta global de cobertura $\ge 85\%$.
