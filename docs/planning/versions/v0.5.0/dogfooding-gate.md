# Portão de Dogfooding — v0.5.0 Sprint 4

> **Status:** ⏳ Aguardando execução pelo Senhor (requer `ANTHROPIC_API_KEY` real; gasta tokens)
> **Regra:** falhou o portão, as Sprints 5–8 continuam pelo Claude Code e o defeito é corrigido antes de repetir (sprint-4.md §9).

## Objetivo
Provar que o ORION + Claude corrige um bug REAL do próprio repositório, com teste e commit passando pelo PEP,
sem nenhuma intervenção do Claude Code.

## Etapa 0 — harness modelo-ponte (sem custo)
Antes da chave real, o Claude Code conduz o ORION real pelo harness `scripts/dogfood/` (README lá). Rodada H1 concluída em 2026-11-07: ver `dogfooding-findings.md`. Repetir o H1 após cada correção.

## Pré-condições
1. Branch de trabalho limpa (`git status` vazio) numa cópia/branch descartável: `git switch -c gate/dogfooding`.
2. `ANTHROPIC_API_KEY` configurada (`/doctor` deve mostrar a chave e o provider Anthropic) e teto do `BudgetGuard` conferido.
3. `orion-agent` iniciado na raiz do repositório, modo **manual** (Shift+Tab até `manual`): toda mutação pede confirmação.
4. Suíte base verde: `pytest tests/ -q`.
5. Escolher o bug ANTES de iniciar (ex.: item do backlog de ruff/mypy, `utcnow()` depreciado, `except/pass` em `edit_file.py`) e escrever o pedido em uma frase.

## Roteiro (cada passo é observável)
| # | Ação do Senhor | Evidência esperada |
|---|---|---|
| 1 | Pedir a correção com `@arquivo` do módulo afetado | O agente abre `todo_write` com o plano; um item `in_progress` por vez |
| 2 | Observar a exploração | Usa `glob`/`grep`/`read_file` (LEVEL_1, sem prompt); nenhuma mutação em modo plano |
| 3 | (Opcional) `Shift+Tab` até `plan` antes do pedido | `exit_plan_mode` abre modal de aprovação do plano; `n` mantém em plano |
| 4 | Aprovar o `edit_file`/`write_file` do teste de regressão | Modal PEP LEVEL_2 com diff; `/diff` mostra o patch |
| 5 | Rodar o teste novo e a suíte | `run_command` pede LEVEL_3; um comando longo vai com `run_in_background` e é lido com `bash_output` |
| 6 | Pedir `ruff check` + `mypy` do módulo | Saída sem novos erros |
| 7 | Pedir o commit (Conventional Commits) | `run_command git commit` aprovado no PEP; `git log -1` confere |
| 8 | Conferir auditoria | `~/.orion/audit.db` registra cada mutação e a decisão do Senhor |

## Critérios de aprovação (todos obrigatórios)
- [ ] Teste de regressão novo falhava ANTES e passa DEPOIS (o agente demonstrou os dois estados).
- [ ] `pytest tests/` verde e `ruff`/`mypy` sem novos erros nos arquivos tocados.
- [ ] Commit criado pelo agente via PEP; nenhum push/merge/tag feito por ele.
- [ ] Zero comandos executados fora do PEP (conferir `audit.db`); nenhuma ação negada contornada.
- [ ] Nenhum travamento da TUI (modal, spinner, shell em background encerrado ao sair).
- [ ] Custo da sessão dentro do teto (`/cost`); cache hit > 0 a partir do 2º passo (`/context`).

## Registro da execução (preencher)
| Campo | Valor |
| :--- | :--- |
| Data / hora | |
| Bug escolhido | |
| Modelo / tier | |
| Passos do agente / tokens / custo | |
| Intervenções manuais necessárias | |
| Resultado | ☐ Aprovado  ☐ Reprovado |
| Defeitos encontrados (viram tarefas) | |

## Observações conhecidas antes de executar
- Em modo `plan`, `web_fetch`/`web_search` (LEVEL_2) são negados como qualquer mutação; a pesquisa na web exige sair do plano.
- Domínios fora da allowlist são negados; para liberar um, criar `~/.orion/web_allowlist.json` (`{"domains": ["exemplo.com"]}`).
- Imagens anexadas (`@arquivo.png`) só chegam a modelos Anthropic; colar da área de transferência não foi implementado.
- Logs do MCP e da CLI: `~/.orion/logs/` (nada disso aparece mais na tela).
