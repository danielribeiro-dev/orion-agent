# ORION-Agent — Active Context (Memória de Sessão de Desenvolvimento)

> **Data de Atualização:** 24/10/2026  
> **Status Atual:** Fase 0 — Fundação Documental, Specs de Arquitetura e Identidade Visual  
> **Regra Suprema:** Nenhuma linha de código em `src/` deve ser escrita até que todas as especificações e contratos estejam 100% documentados e alinhados.

---

## 🎯 Foco Imediato da Sessão Atual
1. **Estruturação Completa da Documentação Mestra:**
   - [x] Criação do repositório limpo `orion-agent` (git init local).
   - [x] Configuração da memória de engenharia em `.claudex/` (`active_context.md`, `progress.md`, `system_patterns.md`, `decisions.md`).
   - [x] Documentação de Arquitetura (`CORE_REACT_ENGINE.md`, `TRIPLE_MEMORY.md`, `TIMELINE_SYSTEM.md`, `AMBIENT_VOICE.md`, `MCP_AND_CHANNELS.md`, `GOVERNANCE_PEP.md`, `MODEL_GATEWAY_COSTS.md`).
   - [x] Identidade Visual e Interface (`ASCII_ART_IDENTITY.md`, `TUI_DESIGN_SYSTEM.md`).
   - [x] Catálogo de 6 Superpoderes modernizados para 2026 (`docs/specs/superpowers/`).
   - [x] Governança de Planejamento, Roadmap e Sprints (`docs/planning/` com templates, Roadmap e sprints da v0.1.0 e v0.2.0).
   - [x] README.md mestre aberto com a visão inspirada em J.A.R.V.I.S., arquitetura e roadmap.

---

## 🧭 Diretrizes Estratégicas Chave (Decisões Alinhadas com o Usuário)
- **Open-Source Core:** O `orion-agent` é um projeto de código aberto. Não há nenhuma ferramenta ou dependência acoplada rigidamente à TalkCode ou TalkAgent. Qualquer integração externa é configurada dinamicamente pelo usuário via MCP, webhooks HTTP ou arquivos de configuração locais.
- **Superando o Hermes:** O ORION acompanha e supera o Hermes em autonomia, memória contínua, execuções headless e proatividade baseada em eventos de SO.
- **Presença Ambiente Headless:** O ORION roda como daemon no boot do sistema operacional. Quando o modo de voz/escuta está ativo, o usuário conversa diretamente com o computador sem a necessidade de manter janelas de terminal abertas. A interface TUI é sob demanda (para desenvolvimento, diffs e tarefas de código).
- **Zero Código Legado:** Nenhuma linha de código Python do repositório antigo foi reaproveitada cegamente. Todo o código do `orion-agent` nascerá limpo, moderno e tipado a partir de especificações formais.
- **Memória Tríplice:** Combinação de Linha do Tempo e Eventos em SQLite FTS5, Memória Semântica com embeddings locais em ONNX/FastEmbed (privativo e offline, sem PyTorch pesado) e Memória Estruturada de Fatos e Decisões.
- **Governança Estrita (PEP):** Modo supervisionado inicial (confirmações explícitas `[Y/n]` para comandos modificadores de sistema/arquivos), evoluindo para níveis configuráveis pelo usuário via `/config`.

---

## 📌 Próximos Passos
1. Sessão de alinhamento e refinamento com o usuário: debate e refinamento fino das habilidades, poderes e etapas de desenvolvimento.
2. Aprovação final da documentação e início da Sprint 1 da v0.1.0 (Setup de Tooling e CLI Skeleton).
