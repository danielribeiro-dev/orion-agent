# Spec — v0.5.0 Claude-Grade Agent (Paridade Claude Code)

> **Status:** 🔄 Em Execução (Sprints 0–3 concluídas)  
> **Criada em:** 2026-11-06  
> **Concluída em:** —  
> **Autor(es):** Daniel Dev & Claude (Pair Programming)  
> **Branch:** `version/v0.5.0`  

---

## 1. Visão Geral & Motivação

### 1.1 Objetivo
Levar o ORION ao nível de agentes de terminal como Claude Code: ao fim da versão, o Senhor roda o ORION com `ANTHROPIC_API_KEY` e programa com ele no dia a dia (inclusive no próprio repositório), com tools, memória, MCPs, decisões, loops, tarefas agendadas, subagents e scripts em segundo plano. A versão também entrega a base do daemon "sempre presente": processo de usuário que acorda com o PC e **não gasta tokens em idle**.

### 1.2 Por que agora?
A v0.4.0 entregou TUI, PEP, memória e MCP, mas **nunca validou um turno com provedor real** e o núcleo agêntico usa protocolo de tool em texto (`<tool_call>`), prompt monolítico e provider único via OpenRouter. Sem provider Anthropic nativo, `tool_use`, prompt caching e auto-compactação, o ORION não consegue substituir o Claude Code. O gate G1–G8 da v1.6.0 para o provider nativo é **revogado** (ADR-020).

### 1.3 O que NÃO é escopo (anti-metas)
- Voz, wake word, STT/TTS (movidos para **v0.6.0**).
- Desktop app Tauri/eDEX (v0.7.0).
- Sandbox Bubblewrap e self-healing (v1.5.0).
- Provedores nativos além de Anthropic (OpenAI/Google continuam via OpenRouter).

---

## 2. Decisões Arquiteturais & Diretrizes de Design

### 2.1 Padrões e Invariantes Aplicáveis
- Brain/Body: `orion.core` não faz I/O direto.
- Tudo mutante passa pelo PEP; subagents, hooks, jobs agendados e daemon **nunca** elevam privilégio; ações nucleares sempre exigem step-up.
- Deny by Default; regras `deny` prevalecem sobre `allow`.
- Runtime somente em `~/.orion/`; segredos nunca no repositório.
- Doc-First; cobertura ≥ 85%; ruff + mypy strict.
- Sem emojis na TUI (`docs/design/CLI_AGENT_RULES.md`).

### 2.2 ADRs desta versão
- **ADR-020:** provider Anthropic nativo adiantado para a v0.5.0 (revoga gates da v1.6.0).
- **ADR-021:** protocolo de mensagens estruturado (content blocks, `tool_use`/`tool_result`, schemas JSON) substitui `<tool_call>` em texto.
- **ADR-022:** daemon event-driven; scheduler e watchers determinísticos; LLM só é chamado por gatilho (zero tokens em idle).
- **ADR-028 a 031 (Sprint 6):** privilégio só diminui nos subagents; tasks em loop de thread com portas; orçamento por agente com reserva; núcleo de agentes agnóstico de provedor.

### 2.3 Dependências e Relações
- **Depende de:** v0.4.0 (TUI, PEP, MCP, memória) fechada.
- **Desbloqueia:** v0.6.0 (voz ambiente sobre o daemon), v1.5.0 (subagents avançados/sandbox).

---

## 3. Divisão em Sprints & Entregáveis

| Sprint | Nome da Sprint | Objetivo Principal | Documento | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Sprint 0** | Higiene & Fundação | Fechar v0.4.0, corrigir docs, ADRs, baseline com provedor real | [`sprint-0.md`](sprints/sprint-0.md) | ✅ Concluída |
| **Sprint 1** | Provider Anthropic Nativo | Messages API, content blocks, caching, retry em stream, failover | [`sprint-1.md`](sprints/sprint-1.md) | ✅ Implementada (live pendente) |
| **Sprint 2** | Loop Agêntico Nativo | `tool_use` estruturado, schemas, tools paralelas, cancelamento | [`sprint-2.md`](sprints/sprint-2.md) | ✅ Implementada |
| **Sprint 3** | Contexto, Sessões & Memória | Auto-compactação, resume/rewind, wiring de memória/skills, decision log | [`sprint-3.md`](sprints/sprint-3.md) | ✅ Implementada |
| **Sprint 4** | Paridade de Ferramentas | Web, glob/grep, todo, ask_user, plan mode, bash em background; **portão de dogfooding** | [`sprint-4.md`](sprints/sprint-4.md) | ✅ Implementada (portão pendente) |
| **Sprint 5** | Extensibilidade & MCP Completo | Settings, regras, hooks, comandos custom, MCP HTTP/OAuth/resources/prompts | [`sprint-5.md`](sprints/sprint-5.md) | ✅ Implementada |
| **Sprint 6** | Subagents & Tasks | 6A: runner, tool `task`, teto de privilégio, orçamento por agente, `/agents`; 6B: background, `/tasks`, worktree, `/loop` (ADR-028 a 031; [estudo](sprint-6-study.md)) | [`sprint-6.md`](sprints/sprint-6.md) | 📋 Spec congelada |
| **Sprint 7** | Daemon, Jobs & Schedules | systemd --user, IPC, scheduler, jobs, notificações, idle = 0 tokens | [`sprint-7.md`](sprints/sprint-7.md) | 📋 Planejando |
| **Sprint 8** | Hardening & Release | Paridade, evals, segurança, doctor, tag `v0.5.0` | [`sprint-8.md`](sprints/sprint-8.md) | 📋 Planejando |

Dogfooding: a partir da conclusão da Sprint 4, as Sprints 5–8 são desenvolvidas usando o próprio ORION (Claude Code como rede de segurança).

---

## 4. Arquitetura Alvo & Componentes Afetados

```
src/orion/
  ├── gateway/providers/anthropic.py     [novo]  Messages API, caching, thinking
  ├── gateway/models.py                  [mod]   ContentBlock, tools, system, cache_control
  ├── core/engine.py                     [mod]   loop com tool_use/tool_result reais
  ├── runtime/tools/                     [mod]   schemas; + glob, grep, web, todo, ask_user, bg shell
  ├── sessions/                          [novo]  transcript JSONL, resume, rewind
  ├── settings/ hooks/ plugins/          [novo]  extensibilidade
  ├── mcp/                               [mod]   HTTP, OAuth, resources, prompts
  ├── agents/                            [novo]  subagents e tasks
  ├── daemon/ scheduler/ notify/         [novo]  presença ambiente
  └── tui/session.py                     [mod]   fiação completa (memória, skills, failover)
```

---

## 5. Matriz de Critérios de Aceite da Versão (DoD Global)

| ID | Cenário | Comportamento Esperado | Como Validar | Status |
|:---|:---|:---|:---|:---|
| CA-01 | Turno real com Claude | Resposta em streaming, uso e cache contabilizados | `ORION_LIVE=1 pytest -m live` | ⏳ Pendente |
| CA-02 | Tool use paralelo | Tools read-only executam em paralelo; mutantes em série e via PEP | `pytest tests/unit/test_engine_toolcalls.py` | ✅ |
| CA-03 | Contexto longo | Auto-compactação a ~80% sem perder tarefa ativa | `pytest tests/unit/test_autocompact.py` | ✅ |
| CA-04 | Resume/Rewind | `--resume` restaura conversa; `/rewind` restaura conversa e arquivos | `pytest tests/unit/test_sessions.py` | ✅ |
| CA-05 | Portão de dogfooding | ORION corrige um bug real do repo, com teste e commit via PEP | roteiro manual documentado | ⏳ Pendente |
| CA-06 | Hooks e regras | Hook `PreToolUse` bloqueia; `deny` vence `allow` | `pytest tests/unit/test_hooks.py tests/unit/test_permission_rules.py` | ✅ |
| CA-07 | MCP completo | HTTP, OAuth, resources e prompts funcionam em servidor falso | `pytest tests/unit/test_mcp_*` | ✅ |
| CA-08 | Subagents | Paralelos, isolados, sem escalar privilégio, com orçamento por agente e agregado | `pytest tests/unit/test_subagents.py tests/unit/test_agent_privilege.py tests/unit/test_agent_budget.py` | ⏳ Pendente |
| CA-13 | Agnosticismo de provedor | `agents/` roda com provider fake sem campos de provedor; tier mutante sem candidato falha sem downgrade | `pytest tests/unit/test_agent_definitions.py tests/unit/test_subagents.py` | ⏳ Pendente |
| CA-14 | Tasks em background | Notificação de término entre turnos com 0 chamadas ao provider; estado sobrevive a reinício | `pytest tests/unit/test_tasks.py` | ⏳ Pendente |
| CA-09 | Schedule sobrevive | Tarefa agendada executa após reiniciar o daemon | `pytest tests/unit/test_scheduler.py` | ⏳ Pendente |
| CA-10 | Idle sem tokens | 1 h de idle com 0 chamadas ao provider | teste de daemon + ledger | ⏳ Pendente |
| CA-11 | Failover | Anthropic indisponível → OpenRouter → Ollama sem downgrade silencioso de modelo de código | `pytest tests/unit/test_failover.py` | ✅ |
| CA-12 | Sem regressão | Suíte da v0.4.0 passa ou é migrada com justificativa | `pytest tests/` | ⏳ Pendente |

---

## 6. Checklist de Conclusão da Spec (Congelamento)

- [ ] Todos os critérios de aceite validados.
- [ ] Testes unitários com cobertura ≥ 85% e zero regressões.
- [ ] Atualização dos documentos de memória em `.claudex/`.
- [ ] Commit por sprint e tag `v0.5.0`.
