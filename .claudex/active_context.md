# O.R.I.O.N — Active Context (Memória de Sessão de Desenvolvimento)

> **Data de Atualização:** 06/11/2026  
> **Status Atual:** v0.4.0 implementada (Sprints 1–5; 1119 testes passando, cobertura 93,70%). v0.5.0 em execução: Sprints 0–2 concluídas (Sprints 1 e 2 aguardando commit).  
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
Providers legados (OpenRouter/Ollama) sem tool calling nativo (movido para a Sprint 3); compactação só manual; `HybridRetriever`, skills, manifest, `EnvironmentMonitor` e circuit breaker não ligados à `AgentSession`; sem resume/rewind, hooks, plugins, subagents, tasks, scheduler, daemon; MCP sem HTTP/OAuth/resources/prompts. Nenhum turno com provedor real foi validado (ver `baseline.md`).

## Pendências de release da v0.4.0 (exigem autorização do Senhor)
Merge de `version/v0.4.0` em `main` e tags `v0.3.0`/`v0.4.0`.

## Próximo Passo
Executar o live test com a chave real (`ORION_LIVE=1 pytest -m live`) e validar um turno com tools de verdade, depois iniciar a **Sprint 3 (Contexto, Sessões & Memória)** mediante comando explícito.
