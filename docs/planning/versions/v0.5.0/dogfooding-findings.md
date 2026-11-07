# Dogfooding — Achados (v0.5.0 Sprint 4)

> Um bloco por achado; não apague os anteriores. Origem: `H` = harness modelo-ponte (`scripts/dogfood/`), `L` = live com chave real.

## Rodada H1 — harness, workspace descartável (2026-11-07)
Cenário: Claude Code como "modelo" do ORION real num pty. Cobertura: `todo_write`, `glob`, `read_file`, `edit_file`
(diff), `run_command` (modal PEP y), `ask_user` (modal, setas+enter), `run_command` em background + `bash_output`,
`enter_plan_mode`, `web_fetch` em plano, `exit_plan_mode` (n e depois y), `/context`, `/exit` (código 0), 3 tools paralelas
com `tool_result` pareados, startup sem ruído. **Corrigiu o bug do workspace de teste ponta a ponta.** Nenhum bloqueante.

| ID | Título | Severidade | Origem | Onde corrigir | Estado |
| :--- | :--- | :--- | :--- | :--- | :--- |
| F-01 | Modal PEP não mostra que o comando roda em background | baixa | H1 | ORION (`panels.describe_action`) | aberto |
| F-02 | Negação automática do modo plano reportada como "user rejected" | média | H1 | ORION (`session._confirm`/PEP) | aberto |
| F-03 | Banner exibe v0.4.0 na branch v0.5.0 | baixa | H1 | ORION (`__version__`/pyproject) | aberto |
| F-04 | Plano de `exit_plan_mode` renderizado como texto cru (`# Plano`) | baixa | H1 | ORION (`panels.render_plan_approval`) | aberto |

### F-01 — Modal PEP não mostra `run_in_background`
- Etapa: harness  Severidade: baixa
- O que fiz: `run_command {"command": "for i in 1 2 3; ...", "run_in_background": true}`
- Esperado × observado: o Senhor deveria ver que o processo continuará rodando após a aprovação; o modal é idêntico ao de um comando síncrono.
- Evidência: tela do modal na rodada H1. Hipótese: `describe_action` só lê `command`.
- Corrigível aqui? sim (uma linha "Execução: em segundo plano" no painel).

### F-02 — Negação do modo plano aparece como rejeição do usuário
- Etapa: harness  Severidade: média
- O que fiz: `enter_plan_mode` e `web_fetch` no mesmo turno.
- Esperado × observado: "negado porque o modo plano é somente leitura"; veio `PEP: user rejected execution of 'web_fetch'.` O modelo pode concluir que o Senhor recusou e insistir/perguntar, em vez de sair do plano.
- Evidência: `tool_result` da req-0008. Hipótese: `_confirm` devolve `False` em PLAN e o runtime usa a mensagem genérica de rejeição.
- Corrigível aqui? sim (mensagem distinta + teste).

### F-03 — Versão do banner
- Banner mostra `v0.4.0`; pyproject tem `0.4.0-alpha`. Hipótese: versão nunca atualizada na v0.5.0. Corrigir na Sprint 8 (release) ou antes.

### F-04 — Plano sem renderização markdown
- O painel de aprovação imprime `# Plano` literal. Hipótese: `Text(plan)` em vez de `rich.markdown.Markdown`.

## Rodada L1 — live com chave real
(pendente)
