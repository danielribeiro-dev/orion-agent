# Sprint — v0.5.3 Sprint 6: Núcleo enxuto e prova

> **Status:** 📋 Aguardando comando de início · **ADR:** 052 · **Achados:** R-16, R-17, M-12 · **CA:** CA-15 a CA-17

## Objetivo
Baixar o custo fixo de cada turno e provar a versão inteira com uma suíte de avaliação e uma rodada real.

## Escopo
1. **Tools adiadas**: no prompt só o nome e uma linha de cada tool fora do núcleo; tool `tool_search(query|select:a,b)` devolve os schemas e os torna chamáveis no turno seguinte. Núcleo sempre carregado: leitura, escrita/edição, `run_command`, `recall`, `session_search`, `ask_user`, `todo_write`, `tool_search`.
2. **Preâmbulo enxuto**: `core/identity.py` reescrito com o princípio do ADR-027 e as regras essenciais; instruções do projeto continuam com teto de 16k caracteres.
3. **Cache de prompt**: ordem estável (preâmbulo → core congelado → instruções do projeto → tools), marcadores de cache no provider Anthropic e OpenRouter quando suportado.
4. **`/context`** sem contagem dupla (M-12), com linhas `core`, `tools`, `projeto`, `recall`, `conversa`.
5. **R-17**: subagent em 429 tenta o próximo modelo free do mesmo tier antes de falhar; sem downgrade silencioso de tier (ADR-031).
6. **Suíte `tests/memory_eval/`** (provider roteirizado, custo zero, PT-BR): identidade sem tool; fato de ontem em outra sessão; correção/superação; pergunta temporal; virada da daily; thread aberta na daily e retomada; precisão do Mordomo (não grava ruído, não sobrescreve CONFIRMED); `rm` com snapshot e `/undo`; senha nunca no contexto/auditoria/logs e nunca preenchida para Nuclear. Relatório de acerto por cenário.
7. **Rodada real** (CA-17): um dia útil do Senhor com `ORION_LIVE=1`, teto no `BudgetGuard`, roteiro em `VERSION.md`; achados viram R-xx.

## Testes
`tests/unit/test_prompt_budget.py` (primeiro turno < 6k tokens), `test_tool_search.py`, `test_subagent_fallback.py`, suíte `memory_eval`.

## Critérios de saída
CA-15 a CA-17 verdes; commit `feat(context): v0.5.3 Sprint 6 — núcleo enxuto e prova`; merge e tag só com confirmação do Senhor.
