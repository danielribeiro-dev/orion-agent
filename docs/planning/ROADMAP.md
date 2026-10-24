# ORION-Agent — Master Evolution Roadmap

> **Visão Geral:** Este documento estabelece o roadmap estratégico e executivo do **ORION-Agent**, desde a fundação inicial do núcleo de orquestração até a consolidação da plataforma de inteligência pessoal de alta autonomia.  
> **Filosofia:** *Estável antes de ambicioso. Seguro antes de autônomo. Documentado antes de codificado.*

---

## 🧭 O Benchmark Estratégico: Superando o Hermes Agent

O ORION utiliza componentes isolados do **Hermes Agent** temporariamente durante as fases iniciais de I/O, mas foi projetado desde o dia zero para **superá-lo estruturalmente** em 4 dimensões essenciais:

| Dimensão | Hermes Agent (Estado Atual) | ORION-Agent (Meta Arquitetural) |
| :--- | :--- | :--- |
| **Memória & Continuidade** | Sessões descartáveis / SQLite isolado por projeto | **Linha do Tempo Contínua & Memória Tríplice:** Sessão unificada persistente desde o boot, FTS5 BM25 + ONNX local, branches contextuais e síntese de checkpoints. |
| **Autonomia & Governança** | Execução direta de tools com guardrails básicos de loop | **Policy Enforcement Point (PEP) Determinístico:** Deny by default, níveis de autonomia configuráveis pelo usuário (`/config`), audit log contínuo e sandboxing com Bubblewrap. |
| **Presença & Interface** | CLI de terminal tradicional | **Presença Ambiente Headless:** Daemon silencioso rodando no boot do SO; escuta e fala sem precisar abrir terminal. TUI interativa sob demanda estilo Antigravity CLI com slash commands dinâmicos (`/`). |
| **Consciência Operacional** | Chamadas diretas ao modelo padrão configurado | **Model Gateway & Cost Ledger em Tempo Real:** Roteamento por orçamento/complexidade, failover com degradação graciosa e tolerância total a falhas offline (*ORION Imortal*). |
| **Extensibilidade** | Plugins e sandboxes proprietários | **Model Context Protocol (MCP) Nativo:** Conexão universal com qualquer servidor MCP e desacoplamento de canais (Telegram, WhatsApp, HTTP). |

---

## 🗺️ Mapa de Versões do ORION-Agent

```
v0.1.0  ── Clean Foundation & Core ReAct Engine ────────────────── [FASE ATUAL]
  │
v0.2.0  ── Continuous Timeline & Triple Memory (FTS5 + FastEmbed)
  │
v0.3.0  ── Model Gateway, Real-Time Cost Ledger & Offline Heartbeat
  │
v0.4.0  ── Interactive TUI (Rich), Dynamic Slash Commands (/) & MCP Client
  │
v0.5.0  ── Ambient Voice Pipeline (Headless Daemon, Wake Word & Tone Mirroring)
  │
v1.0.0  ── Production Release: Autonomous Personal Operating Intelligence
  │
v1.5.0  ── Self-Healing Engine, Bubblewrap Sandboxing & AST Tree-sitter
  │
v2.0.0  ── Ghost Input, Browser CDP Automation & Zero-Knowledge Vault
  │
v2.5.0  ── Spatial Interaction & Hands-Free Vision (Ray Casting & AT-SPI2)
  │
v3.0.0  ── Full Ambient Symbiosis & Multi-Device Coordination
```

---

## 📋 Detalhamento das Versões da Fase Alfa / Fundação

### 🚀 v0.1.0 — Clean Foundation & Core ReAct Engine
* **Status:** 🔄 Em Execução  
* **Foco:** Base de código limpa em Python 3.11+, tipagem Pydantic v2, loop assíncrono ReAct com delimitação estrita de prompt, governança determinística (PEP) e RuntimeProvider com isolamento do Hermes.
* **Documentação:** [`docs/planning/versions/v0.1.0/VERSION.md`](versions/v0.1.0/VERSION.md)
* **Sprints:**
  - `sprint-1`: Setup do ambiente, `pyproject.toml`, CLI Skeleton e Tipagem
  - `sprint-2`: Core ReAct Engine, State Machine e EventBus Assíncrono
  - `sprint-3`: Policy Enforcement Point (PEP), Permissões e RuntimeProvider (Hermes Bridge)
  - `sprint-4`: Bateria de Testes Automatizados, Cobertura 85%+ e Validação E2E

---

### 🧠 v0.2.0 — Continuous Timeline & Triple Memory
* **Status:** 📋 Planejado  
* **Foco:** Eliminação de sessões descartáveis. Implementação da Main Timeline em SQLite WAL com busca léxica FTS5 (BM25), Memória Semântica local via ONNX/FastEmbed (sem PyTorch), Memória Estruturada de perfil/decisões, e motor de branches contextuais com síntese de checkpoints.
* **Documentação:** [`docs/planning/versions/v0.2.0/VERSION.md`](versions/v0.2.0/VERSION.md)

---

### 💰 v0.3.0 — Model Gateway, Cost Ledger & Offline Resilience
* **Status:** 📋 Planejado  
* **Foco:** Roteamento dinâmico multi-provedores (OpenRouter, Gemini, Anthropic, OpenAI, Ollama). Acompanhamento de custos em tempo real em USD/BRL gravados no `metrics.db`. Motor de Heartbeat para detecção de queda de conexão, ativação do modo de sobrevivência local e reconciliação sem conflitos via Event Sourcing (*ORION Imortal*).

---

### 🖥️ v0.4.0 — Dynamic TUI, Slash Commands & Native MCP
* **Status:** 📋 Planejado  
* **Foco:** Interface de terminal inspirada no Antigravity CLI e Claude Code. Banner ASCII exclusivo, status bar reativa, streaming de Markdown, comandos dinâmicos lidos de pastas (`/plan`, `/config`, `/compact`, `/cost`, `/timeline`), menções `@` a arquivos e cliente nativo do Model Context Protocol (MCP stdio/SSE).

---

### 🎙️ v0.5.0 — Ambient Mode & Headless Voice Pipeline
* **Status:** 📋 Planejado  
* **Foco:** Transformação no J.A.R.V.I.S. real. Inicialização em background via systemd user daemon no boot do Linux. Escuta contínua de wake word leve (openWakeWord), transcrição local (Faster-Whisper), síntese ultrarrápida (Piper TTS) com adaptação dinâmica de tom e concisão (*Tone-Mirroring*), operando sem necessidade de janelas de terminal abertas.

---

### 🛡️ v1.0.0 — Production Milestone: The Personal Operating Intelligence
* **Status:** 📋 Marco de Produção  
* **Foco:** Fechamento da Fase 1. Estabilidade militar, documentação completa de contribuição comunitária, zero vazamentos de dados, pacotes de distribuição binária e suíte de auditoria de segurança rigorosa.

---

## 👥 Guia para Desenvolvedores e Novos Contribuidores

Se você está chegando agora para contribuir com o **ORION-Agent**:

1. **Entenda onde estamos:** Consulte o status da versão ativa em [`docs/planning/versions/`](versions/) e o backlog em `.claudex/progress.md`.
2. **Respeite o fluxo de Sprints:** Cada versão é dividida em sprints atômicas em `docs/planning/versions/<versao>/sprints/`. Cada sprint tem seu escopo estrito, contratos de código e critérios de aceite (Definition of Done).
3. **Padrão Doc-First:** Nunca abra um Pull Request com código que altere contratos ou adicione features sem antes atualizar ou criar a especificação correspondente.
4. **Zero Código não Testado:** Qualquer alteração no Core ou Runtime deve ser acompanhada de testes unitários automatizados.
