<div align="center">

```text
       /\
      /  \        ___  ____  _ ____  _   _
     / /\ \      / _ \|  _ \(_)  _ \| \ | |
    / /__\ \    | | | | |_) | | | | |  \| |
   / /    \ \   | |_| |  _ <| | |_| | |\  |
  /_/      \_\   \___/|_| \_\_|\____/|_| \_|
   *    *    *   [ PERSONAL OPERATING INTELLIGENCE ]
```

**O.R.I.O.N — Operational Reasoning & Intelligence Orchestration Network**  
*O Sistema Pessoal de Inteligência, Orquestração e Presença Contínua*

*Inspirado no conceito de J.A.R.V.I.S. — projetado para a vida real como uma plataforma aberta, soberana, extensível e comercialmente viável.*

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?style=flat-square&logo=python)](https://python.org)
[![Platform](https://img.shields.io/badge/Plataforma-Linux-orange?style=flat-square&logo=linux)](https://kernel.org)
[![Status](https://img.shields.io/badge/Status-v0.1.0_Clean_Foundation-green?style=flat-square)]()

</div>

---

## 🌟 O que é o O.R.I.O.N?

O **O.R.I.O.N** é um sistema pessoal de inteligência e orquestração operacional que acompanha o usuário ao longo do tempo. Ele aprende com as informações autorizadas que recebe, coordena modelos e agentes, executa tarefas reais no computador e atua como um **piloto administrativo e técnico pessoal**.

Ele combina os melhores paradigmas do mercado em uma plataforma coesa:
- **Action-Observation Event Stream & Event Sourcing (Inspirado no OpenHands):** Loop cognitivo assíncrono onde cada passo e retorno ambiental são imutáveis e auditáveis.
- **5 Ferramentas Primitivas Nativas Cirúrgicas (Inspirado no Claude Code):** `run_command`, `read_file`, `write_file`, `edit_file` (substituição exata de bloco) e `search_files`, garantindo independência total de muletas externas.
- **Subsistema de Artefatos & Subagentes Reativos (Inspirado no Antigravity CLI):** Geração de documentos estruturados (planos, relatórios, walkthroughs) fora da janela de chat e delegação sem polling.
- **Presença Ambiente e Voz Headless:** Inicia junto com o computador em segundo plano via systemd daemon. Você conversa diretamente com o sistema sem precisar abrir janelas ou terminais.
- **Linha do Tempo Contínua & Memória Tríplice:** Combinação de busca temporal exata (SQLite FTS5 / BM25), recuperação conceitual (FastEmbed / ONNX local offline) e fatos estruturados tipados.
- **Roteamento Inteligente & Livro-Razão em Tempo Real:** Modos `auto` (chaveamento autônomo entre modelos de raciocínio profundo como Claude Opus/Sonnet e de execução rápida como Gemini Flash/Qwen Coder) e `fixed`, com livro-razão financeiro de tokens em USD/BRL exibido no CLI.
- **Extensibilidade Universal (MCP & Satélites):** Cliente nativo do *Model Context Protocol* (MCP) e suporte a canais (Telegram, WhatsApp, Webhooks HTTP). Zero acoplamento com ferramentas proprietárias.

---

## 🏛️ Arquitetura em Destaque

```
┌────────────────────────────────────────────────────────────────────────┐
│                        TUI / CLI Layer (Interface)                     │
│    (Rich / Prompt-Toolkit: Streaming, Diffs, Tokens/Custos, Slash /)   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                  Action-Observation Event Stream                       │
│    (ReAct Loop Assíncrono, Delimitadores Formais, Turn Budgeting)      │
├───────────────────────────────────┬────────────────────────────────────┤
│         Sistema de Memória        │         Camada de Execução         │
│  • Linha do Tempo & FTS5 (BM25)   │  • PEP (Policy Enforcement Point)  │
│  • FastEmbed Local (ONNX Vector)  │  • LocalRuntimeProvider Nativo     │
│  • Fatos Estruturados & Decisões  │  • 5 Ferramentas Primitivas        │
│  • Branches & Checkpoint Synthesis│  • Model Context Protocol (MCP)    │
└───────────────────────────────────┴────────────────────────────────────┘
```

---

## 🚀 Filosofia de Desenvolvimento

1. **Open-Source & Soberano por Princípio:** O `orion-agent` é aberto e universal. Nenhuma ferramenta proprietária é hardcodada no núcleo; tudo é modular.
2. **Deny by Default:** Nenhuma ação modificadora ou destrutiva ocorre no sistema sem validação do PEP e aprovação explícita no modo supervisionado.
3. **Memória Não é Apenas Vetor:** A inteligência contextual exige temporalidade e fatos confirmados, e não apenas proximidade de cosseno.
4. **Verificação de Resultados:** Tentativa $\ne$ Conclusão. Uma tarefa só é declarada pronta após evidência verificada.
5. **Doc-First Engineering:** Toda fase é especificada formalmente antes de qualquer código ser escrito.

---

## 🗺️ Roadmap de Evolução & Planejamento de Versões

- **Roadmap Executivo Geral:** [`docs/planning/ROADMAP.md`](docs/planning/ROADMAP.md)
- **Planejamento de Versões & Sprints:** [`docs/planning/versions/`](docs/planning/versions/)
- **Especificações de Arquitetura:** [`docs/architecture/`](docs/architecture/)
- **Catálogo de Superpoderes (2026):** [`docs/specs/superpowers/`](docs/specs/superpowers/)

```text
v0.1.0  ← ATUAL — Clean Foundation & Core ReAct Engine (Sprints 1 a 4)
v0.2.0  — Cognitive Continuity: Triple Memory, Agent Skills Standard & Dynamic Compaction (FTS5 + FastEmbed + SKILL.md + Compactor)
v0.3.0  — Model Gateway, Real-Time Cost Ledger & Offline Heartbeat
v0.4.0  — High-Performance Stream CLI (orion-agent), Slash Commands (/) & Native MCP Client
v0.5.0  — Ambient Voice Pipeline (Headless Daemon, Wake Word & Tone Mirroring)
v1.0.0  — Production Release: Autonomous Personal Operating Intelligence
```

---

## 📄 Licença

Este projeto é distribuído sob os termos da [Licença Apache 2.0](LICENSE).
