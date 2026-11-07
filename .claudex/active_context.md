# O.R.I.O.N — Active Context (Memória de Sessão de Desenvolvimento)

> **Data de Atualização:** 07/11/2026  
> **Status Atual:** v0.4.0 implementada. v0.5.0 em execução: Sprints 0–4 implementadas (Sprint 4 aguardando commit e **portão de dogfooding**; cobertura 94%).  
> **Fase Ativa:** v0.5.0 "Claude-Grade Agent" — meta: programar com Claude rodando pelo ORION (`ANTHROPIC_API_KEY`), com tools, memória, MCPs, decisões, loops, schedules, subagents e jobs em segundo plano.  
> **Branch Ativo:** `version/v0.5.0`  
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

## Próximo Passo
Commit da Sprint 4 (`feat(tools): v0.5.0 Sprint 4 — Paridade de Ferramentas`), então o Senhor executa o portão de dogfooding (`docs/planning/versions/v0.5.0/dogfooding-gate.md`) com `ANTHROPIC_API_KEY` real, em modo `manual`. Aprovado, as Sprints 5–8 passam a ser desenvolvidas pelo próprio ORION; reprovado, seguem pelo Claude Code e os defeitos são corrigidos. Também pendente: `ORION_LIVE=1 pytest -m live` (cache hit e auto-compactação).
