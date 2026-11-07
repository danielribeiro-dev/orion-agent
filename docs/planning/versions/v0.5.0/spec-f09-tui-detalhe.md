# Spec — F-09: Nível de detalhe da TUI (tools, diffs, raciocínio)

> **Status:** rascunho para aprovação do Senhor (nenhuma linha de `src/` até a aprovação — Doc-First).
> **Origem:** `dogfooding-findings.md` F-09. **Alvo:** `src/orion/tui/stream_renderer.py`, `diff_viewer`, `session.py`.

## 1. Problema
Card atual: `✔ Edit: calc.py · 0.0s · +1 / -1` + diff. Faltam parâmetros úteis do comando, saída ao vivo,
duração significativa, raciocínio em bloco e contexto nos diffs, frente a Claude Code/Hermes.

## 2. Requisitos
1. **Cabeçalho do card:** `● Bash(pytest -q)` em execução; ao concluir `✔`/`✖` + duração + `exit N`. Parâmetros longos truncados em 1 linha.
2. **Saída ao vivo** de `run_command`: últimas 5 linhas em região `Live` enquanto roda; ao fim, colapso 3+2 existente (`Alt+E` expande).
3. **Falhas:** `✖` mostra o erro e a saída completa colapsada (já recebem a saída desde o F-06).
4. **Diffs:** cabeçalho com caminho e `+N / -M`, 3 linhas de contexto, números de linha, linhas longas com quebra; diffs > 40 linhas colapsam com `Alt+E`.
5. **Raciocínio (live):** bloco `▼ Raciocínio formulado em Xs` colapsável (regra 4 de `CLI_AGENT_RULES.md`); validar com chave real (a ponte não emite thinking, N-01).
6. **Tools paralelas:** um card por chamada, agrupadas sob o turno.

## 3. Fora de escopo
Novos glifos (usar só os aprovados), cores fora de `ORION_COLORS`, emojis.

## 4. Critérios de aceite
- Testes de renderer com `Console` gravando saída (sem TTY) para cada requisito.
- `ruff`, `mypy`, cobertura ≥ 85%; checklist da seção 4 de `CLI_AGENT_RULES.md`.
- Validação visual pelo harness (`scripts/dogfood/`) e, depois, na rodada L1.

## 5. Decisão pendente
Em qual sprint entra: proposta = nova sprint de interface após a Sprint 5, antes do hardening (Sprint 8).
