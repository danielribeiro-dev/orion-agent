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

**O Sistema Pessoal de Inteligência, Orquestração e Presença Contínua**

*Inspirado no conceito de J.A.R.V.I.S. — projetado para a vida real como uma plataforma aberta, extensível e comercialmente viável.*

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?style=flat-square&logo=python)](https://python.org)
[![Platform](https://img.shields.io/badge/Plataforma-Linux-orange?style=flat-square&logo=linux)](https://kernel.org)
[![Status](https://img.shields.io/badge/Status-Fase_0:_Funda%C3%A7%C3%A3o-green?style=flat-square)]()

</div>

---

## 🌟 O que é o ORION?

O **ORION** é um sistema pessoal de inteligência e orquestração operacional que acompanha o usuário ao longo do tempo. Ele aprende com as informações autorizadas que recebe, coordena modelos e agentes, executa tarefas reais no computador e atua como um **piloto administrativo e técnico pessoal**.

Ele combina:
- **Presença Ambiente e Voz Headless:** Inicia junto com o computador em segundo plano. Quando a voz está ativa, você conversa diretamente com o sistema sem precisar abrir janelas ou terminais.
- **Linha do Tempo Contínua:** Não existem sessões descartáveis. O ORION mantém o contexto histórico acumulado, criando ramificações (*branches*) para projetos complexos e sintetizando os aprendizados de volta na linha do tempo principal.
- **Memória Tríplice:** Combinação de busca temporal exata (SQLite FTS5 / BM25), recuperação conceitual (FastEmbed / ONNX local sem dependências pesadas) e fatos estruturados tipados.
- **Roteamento Inteligente e Consciência de Custos:** Escolhe dinamicamente entre modelos econômicos, intermediários, avançados ou locais (OpenRouter, Gemini, Claude, OpenAI, Ollama), com livro-razão financeiro de tokens em tempo real.
- **Interface TUI Sob Demanda:** Terminal dinâmico estilo Antigravity CLI e Claude Code com streaming de Markdown, comandos por barra (`/`), suporte a arquivos `@` e visualizador de diffs com syntax highlighting.
- **Extensibilidade Universal (MCP & Satélites):** Cliente nativo do *Model Context Protocol* (MCP) e suporte a canais (Telegram, WhatsApp, Webhooks HTTP). Zero acoplamento com ferramentas proprietárias.

---

## 🏛️ Arquitetura em Destaque

```
┌────────────────────────────────────────────────────────────────────────┐
│                        TUI / CLI Layer (Interface)                     │
│    (Rich / Prompt-Toolkit: Streaming, Diffs, Slash Commands /)         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                    Orchestration & State Machine                       │
│    (ReAct Loop Assíncrono, Delimitadores Formais, Guardrails)          │
├───────────────────────────────────┬────────────────────────────────────┤
│         Sistema de Memória        │         Camada de Execução         │
│  • Linha do Tempo & FTS5 (BM25)   │  • PEP (Policy Enforcement Point)  │
│  • FastEmbed Local (ONNX Vector)  │  • RuntimeProvider (Clean Adapter) │
│  • Fatos Estruturados & Decisões  │  • Model Context Protocol (MCP)    │
│  • Branches & Checkpoint Synthesis│  • Ferramentas Nativas (AST Editor)│
└───────────────────────────────────┴────────────────────────────────────┘
```

---

## 🚀 Filosofia de Desenvolvimento

1. **Open-Source por Princípio:** O `orion-agent` é aberto e universal. Nenhuma ferramenta proprietária é hardcodada no núcleo; tudo é plugável.
2. **Deny by Default:** Nenhuma ação modificadora ou destrutiva ocorre no sistema sem validação do PEP e aprovação explícita no modo supervisionado.
3. **Memória Não é Apenas Vetor:** A inteligência contextual exige temporalidade e fatos confirmados, e não apenas proximidade de cosseno.
4. **Verificação de Resultados:** Tentativa $\ne$ Conclusão. Uma tarefa só é declarada pronta após evidência verificada.
5. **Doc-First Engineering:** Toda fase é especificada formalmente antes de qualquer código ser escrito.

---

## 🗺️ Roadmap de Evolução & Planejamento de Versões

O desenvolvimento do ORION é governado por planejamento formal, com versões divididas em sprints executáveis e critérios de aceite comprovados:

- **Roadmap Executivo Geral:** [`docs/planning/ROADMAP.md`](docs/planning/ROADMAP.md)
- **Planejamento de Versões & Sprints:** [`docs/planning/versions/`](docs/planning/versions/)
- **Especificações de Arquitetura:** [`docs/architecture/`](docs/architecture/)
- **Catálogo de Superpoderes (2026):** [`docs/specs/superpowers/`](docs/specs/superpowers/)

```text
v0.1.0  ← ATUAL — Clean Foundation & Core ReAct Engine (Sprints 1 a 4)
v0.2.0  — Continuous Timeline & Triple Memory (FTS5 + FastEmbed + Branches)
v0.3.0  — Model Gateway, Real-Time Cost Ledger & Offline Heartbeat
v0.4.0  — Interactive TUI (Rich), Dynamic Slash Commands (/) & MCP Client
v0.5.0  — Ambient Voice Pipeline (Headless Daemon, Wake Word & Tone Mirroring)
v1.0.0  — Production Release: Autonomous Personal Operating Intelligence
```

---

## 📄 Licença

Este projeto é distribuído sob os termos da [Licença Apache 2.0](LICENSE).
