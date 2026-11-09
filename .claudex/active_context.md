# O.R.I.O.N — Active Context (Memória de Sessão de Desenvolvimento)

> **Data de Atualização:** 07/11/2026  
> **Status Atual:** v0.4.0 implementada. v0.5.0 em execução: Sprints 0–5 concluídas; **Sprint 6 (Subagents & Tasks) implementada (6A + 6B)** (ADR-028 a 031, estudo em `sprint-6-study.md`). Visão ADR-027 (memória viva, protocolos = skills dinâmicas) documentada em `docs/planning/vision/`. Portão de dogfooding pendente; cobertura 94%.  
> **Fase Ativa:** v0.5.0 "Claude-Grade Agent" — meta: programar com Claude rodando pelo ORION (`ANTHROPIC_API_KEY`), com tools, memória, MCPs, decisões, loops, schedules, subagents e jobs em segundo plano.  
> **Branch Ativo:** `ccr-a47cd494-1hj1wu` (a partir de `feat/v0.5.0-sprint-6`)  
> **Regra Suprema:** Nenhuma linha de código em `src/` é escrita sem o comando explícito de início da Sprint correspondente (Doc-First).

---

## Estado
- Especificação: `docs/planning/versions/v0.5.0/VERSION.md` e `sprints/sprint-0.md` … `sprint-8.md`.
- ADRs novos: 020 (provider Anthropic antecipado), 021 (content blocks em vez de `<tool_call>`), 022 (daemon com zero token em idle). Ver `.claudex/decisions.md`.
- Voz/wake word foi para a v0.6.0. Dogfooding (desenvolver pelo próprio ORION) começa após o portão da Sprint 4.
- Cada sprint roda em sessão separada; ler `CLAUDE.md`, este arquivo e o `sprint-N.md` correspondente antes de começar.

## Lacunas conhecidas (alvo das Sprints 1–8)
Sem hooks, plugins, settings/regras, comandos custom, subagents, tasks, scheduler, daemon; MCP sem HTTP/OAuth/resources/prompts. Tools de paridade entregues na Sprint 4. Nenhum turno com provedor real foi validado (ver `baseline.md`).

## Pendências de release da v0.4.0 (exigem autorização do Senhor)
Merge de `version/v0.4.0` em `main` e tags `v0.3.0`/`v0.4.0`.

## Próximo Passo (retomar aqui)
**Sprint 6 concluída (6A + 6B)** em 09/11/2026: dois commits locais em `ccr-a47cd494-1hj1wu` (a partir de `feat/v0.5.0-sprint-6`), **não enviados/mergeados**. Entregue: subagents sob teto de privilégio no PEP e orçamento com reserva (6A); background em thread dedicada, `tasks.db`, `task_*`/`send_message`, notificação por evento entre turnos, worktree que falha fechado e `/loop` com triagem (6B). Detalhes e desvios: `progress.md` e `sprints/sprint-6.md` §8.1/§8.2. **Próximo: Sprint 7** (daemon systemd --user, IPC, scheduler durável/cron, jobs, notificações desktop/Telegram, idle = 0 tokens), com comando explícito do Senhor; ela reaproveita `TaskStorePort`/`NotifierPort`/`ExecutorPort` e o envelope `AgentEventEnvelope`.
Pendências que dependem do Senhor: (1) push/merge de `feat/v0.5.0-sprint-5`, `feat/v0.5.0-sprint-6` e `gate/dogfooding-v0.5.0`; (2) validar em TTY real o modal de escalada, o pedido de confiança do projeto, `/mcp auth`, `/agents`, as linhas de progresso dos filhos, a toolbar `tasks N ● · M ✔` e `/tasks`/`/loop`; (3) rodada live no `explore` (`ORION_LIVE=1`, `ANTHROPIC_API_KEY`, teto no `BudgetGuard`).
Notas de ambiente: `aiohttp` é importado por `gateway/providers/local_ollama.py` mas não está declarado no `pyproject.toml` (2 arquivos de teste não coletam sem ele); `test_vector_store` baixa o modelo ONNX (precisa de rede).

Histórico anterior (gate de dogfooding):
Estado: branch `gate/dogfooding-v0.5.0` (commits locais NÃO enviados ao remoto após `00eaeae`; `version/v0.5.0` = Sprint 4 `a0c42bb`, já no remoto). Harness modelo-ponte em `scripts/dogfood/` (README lá); rodadas H1 (pty) e H2 (aba do Senhor) concluídas — achados em `docs/planning/versions/v0.5.0/dogfooding-findings.md`.
1. **Feito (não commitado):** F-01 a F-08 corrigidos com testes de regressão (F-06 engine devolve erro + saída; F-02 `Rejection` no PEP; F-03 versão 0.5.0-alpha e banner via `__version__`; F-07/F-08 réguas dinâmicas acima/abaixo do input no HSplit (validadas em pty) + texto digitado em negrito, regra 3 de `CLI_AGENT_RULES.md` reescrita).
2. **Compactação/poda:** coberta por testes de sessão (`test_autocompact.py`); falta validar pela ponte (`/compact` e saídas enormes de tool) e depois no live.
3. **F-09:** spec em `docs/planning/versions/v0.5.0/spec-f09-tui-detalhe.md`, aguardando aprovação e sprint.
4. Só então a rodada live com `ANTHROPIC_API_KEY` (criar conta de API; o plano Pro não cobre) e decidir push/merge com o Senhor.
