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

## Próximo Passo (retomar aqui)
Estado: branch `gate/dogfooding-v0.5.0` (commits locais NÃO enviados ao remoto após `00eaeae`; `version/v0.5.0` = Sprint 4 `a0c42bb`, já no remoto). Harness modelo-ponte em `scripts/dogfood/` (README lá); rodadas H1 (pty) e H2 (aba do Senhor) concluídas — achados em `docs/planning/versions/v0.5.0/dogfooding-findings.md`.
1. Corrigir **F-06** (alta): `engine._execute_action` descarta `RuntimeResult.output` quando a tool falha; devolver erro + saída; teste de regressão.
2. Validar **compactação/poda** (nunca disparou: janela 1M): `/compact` e saídas enormes de tool pelo harness; depois live.
3. Corrigir **F-02** (negação do modo plano dita "user rejected"), F-01, F-03, F-04 e **F-05** (`ctl attach` deve limpar `home/`).
4. Decidir design de **F-07/F-08** (destaque do prompt, réguas do input; atualizar `CLI_AGENT_RULES.md`) e abrir spec para **F-09** (detalhe de tools/diffs/raciocínio).
5. Só então a rodada live com `ANTHROPIC_API_KEY` (criar conta de API; o plano Pro não cobre) e decidir push/merge com o Senhor.
