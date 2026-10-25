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
v0.1.0  ── Clean Foundation & Core ReAct Engine ────────────────── [FASE ATUAL: Sprints 1, 2, 3 Concluídas]
  │        (5 Ferramentas Nativas, Action-Observation, PEP e Artefatos)
v0.2.0  ── Cognitive Continuity: Triple Memory, Agent Skills Standard & Dynamic Compaction [ESPECIFICAÇÃO PRONTA]
  │        (SQLite WAL FTS5 + ONNX FastEmbed Local + Fatos RRF + SKILL.md Engine + Compactor)
v0.3.0  ── Model Gateway, Real-Time Cost Ledger, Offline Resilience & Nuclear Safety [ESPECIFICAÇÃO PRONTA]
  │        (Prioridade OpenRouter, Dynamic Auto-Routing, metrics.db, Failover < 2s Qwen Coder 1.5B/3B, Popup do SO)
v0.4.0  ── High-Performance Stream CLI, Slash Commands (/) & Native MCP [ESPECIFICAÇÃO PRONTA]
  │        (orion-agent CLI, prompt_toolkit + Rich, Banner Mão Cósmica, 20 Slash Commands, MCP)
v0.5.0  ── Ambient Mode & Headless Voice Pipeline
  │        (Systemd Boot Daemon, openWakeWord, Faster-Whisper, Piper TTS, "Senhor, posso executar...")
v1.0.0  ── Production Release: Autonomous Personal Operating Intelligence
  │        (Blindagem de Segurança Militar, Pacotes Binários e Multiplataforma)
v1.5.0  ── Self-Healing Engine, Bubblewrap Sandboxing & Dynamic Subagents
v2.0.0  ── Ghost Input (/dev/uinput), Chrome CDP Automation & Zero-Knowledge Vault
v2.5.0  ── Spatial Interaction & Hands-Free Burst Vision (Ray Casting & AT-SPI2)
v3.0.0  ── Full Ambient Symbiosis & Multi-Device Distributed Coordination
```

---

## 📋 3. Detalhamento das Versões Iniciais Especificadas

### 🚀 v0.1.0 — Clean Foundation & Core ReAct Engine
* **Status:** 🔄 Sprints 1, 2 e 3 Concluídas (168 testes unitários passando) | Sprint 4 Pendente  
* **Foco:** Base de código limpa em Python 3.11+, tipagem Pydantic v2, loop assíncrono ReAct baseado em **Action-Observation Event Stream**, delimitação estrita de prompts, 5 Ferramentas Primitivas Nativas de SO (`run_command`, `read_file`, `write_file`, `edit_file`, `search_files`), governança determinística (PEP) e subsistema inicial de Artefatos.
* **Documentação:** [`docs/planning/versions/v0.1.0/VERSION.md`](versions/v0.1.0/VERSION.md)

### 🧠 v0.2.0 — Cognitive Continuity: Triple Memory, Agent Skills Standard & Dynamic Compaction
* **Status:** 📋 Especificação Formalizada e Congelada para Execução  
* **Foco:** Memória Tríplice (SQLite WAL FTS5 BM25 + ONNX FastEmbed local `bge-small-en-v1.5` + Fatos estruturados anti-envenenamento com ciclo tipado), Fusão Híbrida RRF (< 1.500 tokens), Padrão Universal `Agent Skills` (`SKILL.md`) com Progressive Disclosure em 3 fases e Dynamic Context Compactor (auto-compaction a 80% e comando `/compact`).
* **Documentação:** [`docs/planning/versions/v0.2.0/VERSION.md`](versions/v0.2.0/VERSION.md)

### ⚡ v0.3.0 — Model Gateway, Real-Time Cost Ledger, Offline Resilience & Nuclear Safety
* **Status:** 📋 Especificação Formalizada e Congelada para Execução  
* **Foco:** Abstração agnóstica de modelos com provedor prioritário OpenRouter, Dynamic Auto-Routing por complexidade de turno (Fast/Lite, Balanced, Heavy Frontier), Livro-Razão de Custos em tempo real em SQLite WAL (`~/.orion/metrics.db`) com cálculo USD/BRL e teto orçamentário diário, **ORION Imortal** (failover offline $< 2$s para `qwen2.5-coder:1.5b/3b` local no Ollama), e **Autonomia Adaptativa com Nuclear Step-Up Auth** (cache de comandos conhecidos no PEP + popup obrigatório de senha do SO para ações destrutivas).
* **Documentação:** [`docs/planning/versions/v0.3.0/VERSION.md`](versions/v0.3.0/VERSION.md)

### 🖥️ v0.4.0 — High-Performance Stream CLI, Slash Commands & Native MCP
* **Status:** 📋 Especificação Formalizada e Congelada para Execução  
* **Foco:** Ponto de entrada oficial `orion-agent`, Stream CLI ergonômico com `prompt_toolkit` (autocomplete flutuante de `/` e expansão de arquivos com `@`) e `Rich.Live` (streaming token a token, diffs coloridos e banner adaptativo da Mão Cósmica com Buraco Negro), Catálogo Oficial dos 20 Slash Commands e Cliente nativo MCP (stdio e SSE).
* **Documentação:** [`docs/planning/versions/v0.4.0/VERSION.md`](versions/v0.4.0/VERSION.md)

---

## 👥 4. Guia para Desenvolvedores e Contribuidores

1. **Entenda onde estamos:** Consulte o status da versão ativa em [`docs/planning/versions/`](versions/) e o backlog em `.claudex/progress.md`.
2. **Respeite o fluxo de Sprints:** Cada versão é dividida em sprints atômicas em `docs/planning/versions/<versao>/sprints/`. Cada sprint tem seu escopo estrito, contratos de código e critérios de aceite (Definition of Done).
3. **Padrão Doc-First:** Nenhuma linha de código em `src/` é escrita sem antes atualizar ou criar a especificação correspondente.
4. **Zero Código não Testado:** Qualquer alteração no Core ou Runtime deve ser acompanhada de testes automatizados com meta global de cobertura $\ge 85\%$.
