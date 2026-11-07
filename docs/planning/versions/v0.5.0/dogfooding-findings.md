# Dogfooding — Achados (v0.5.0 Sprint 4)

> Um bloco por achado; não apague os anteriores. Origem: `H` = harness modelo-ponte (`scripts/dogfood/`), `L` = live com chave real.

## Rodada H1 — harness, workspace descartável (2026-11-07)
Cenário: Claude Code como "modelo" do ORION real num pty. Cobertura: `todo_write`, `glob`, `read_file`, `edit_file`
(diff), `run_command` (modal PEP y), `ask_user` (modal, setas+enter), `run_command` em background + `bash_output`,
`enter_plan_mode`, `web_fetch` em plano, `exit_plan_mode` (n e depois y), `/context`, `/exit` (código 0), 3 tools paralelas
com `tool_result` pareados, startup sem ruído. **Corrigiu o bug do workspace de teste ponta a ponta.** Nenhum bloqueante.

| ID | Título | Severidade | Origem | Onde corrigir | Estado |
| :--- | :--- | :--- | :--- | :--- | :--- |
| F-01 | Modal PEP não mostra que o comando roda em background | baixa | H1 | ORION (`panels.describe_action`) | corrigido |
| F-02 | Negação automática do modo plano reportada como "user rejected" | média | H1 | ORION (`session._confirm`/PEP) | corrigido |
| F-03 | Banner exibe v0.4.0 na branch v0.5.0 | baixa | H1 | ORION (`__version__`/pyproject) | corrigido |
| F-04 | Plano de `exit_plan_mode` renderizado como texto cru (`# Plano`) | baixa | H1 | ORION (`panels.render_plan_approval`) | corrigido |

## Rodada H2 — harness na aba do Senhor, TUI real (2026-11-07)
Cenário: o Senhor usou o ORION na própria aba; o Claude Code respondeu como modelo. Bug da soma corrigido de ponta a ponta
(`todo_write`, `read_file`, `run_command` com PEP, `edit_file`, teste final). Avaliação do Senhor: visual "incrivelmente bom"; ajustes abaixo.

| ID | Título | Severidade | Origem | Onde corrigir | Estado |
| :--- | :--- | :--- | :--- | :--- | :--- |
| F-05 | `ctl attach` não limpa `home/`: memória de rodadas anteriores vaza (auto-recall) | baixa | H2 | harness (`ctl.py`) | corrigido |
| F-06 | `run_command` com exit != 0 devolve ao modelo só "exited with code N", sem a saída | **alta** | H2 | ORION (`engine._execute_action`) | corrigido |
| F-07 | Prompt do usuário não se destaca das respostas do ORION (sem variação de cor/fundo) | média | H2 | ORION (TUI) | corrigido (texto digitado em negrito) |
| F-08 | Sem réguas/bordas acima e abaixo do input: não se vê onde a resposta acaba e o input começa | média | H2 | ORION (`prompt.py`) | corrigido (réguas acima e abaixo no container, dinâmicas) |
| F-09 | Raciocínio, execução de tools e diffs mais superficiais que Claude Code/Hermes | média | H2 | ORION (`stream_renderer`) | aberto, spec aberta: `spec-f09-tui-detalhe.md` |

### F-05 — Memória vaza entre rodadas do harness
- O que fiz: `ctl attach` após a rodada H1. Observado: `recalled_context` com o episódio da H1 já no 1º pedido. Causa verificada: `attach` apaga só arquivos de `bridge/`; `bridge/home/` (timeline, facts) permanece. Corrigir: `attach`/`start` limparem `home/` (opção `--keep-home`).

### F-06 — Saída perdida quando o comando falha
- O que fiz: `run_command {"command": "python -m pytest -q test_calc.py"}` com teste falhando.
- Esperado × observado: o modelo deveria receber o traceback; recebeu só `run_command: process exited with code 1.` (req-0004).
- Hipótese (a verificar no código): `engine._execute_action` usa `result.output if result.success else result.error` e descarta `RuntimeResult.output` dos comandos que falham, embora `run_command` o preencha.
- Corrigível aqui? sim: devolver erro + saída; teste de regressão em `test_engine_toolcalls.py`.

### F-07/F-08 — Separação visual entre usuário e agente
- Observação do Senhor: o prompt não tem cor/fundo próprio e não há traço acima/abaixo do campo; só a seta `❯` separa. `prompt.py` removeu os "túneis" de propósito (comentário no código), mas `CLI_DESIGN_SYSTEM.md` define `border_subtle` para "linhas divisórias e réguas". Decidir: régua fina em `border_subtle` acima/abaixo do input e/ou eco do pedido do usuário com cor distinta. Exige atualizar `CLI_AGENT_RULES.md`.

### N-01 — Notas do harness (não são defeitos do ORION)
- **Contagem de tokens:** o provider-ponte estima `caracteres/4` só das mensagens (ignora system prompt ≈290 tokens e tools ≈2,7k); o `out` ≈ texto do modelo. A soma por chamada está correta. Valor absoluto só é confiável no live.
- **Raciocínio não aparece:** a ponte não emite thinking; o bloco de raciocínio só poderá ser avaliado no live.
- **Memória (verificada em `home/`):** transcript 20 mensagens + snapshot de arquivo, Timeline 13 eventos/6 embeddings (recall funcionando), auditoria 12 registros, **fatos duráveis = 0** (só `memorize`/`record_decision` gravam; por desenho).
- **Pendente de validação:** poda (60%) e compactação (80%) nunca dispararam (janela 1M, uso ≈9k). Testar com `/compact` e com saídas enormes de tool no harness; depois no live.

### F-09 — Nível de detalhe
- Observação do Senhor (a parte de pensamentos é artefato do harness, ver N-01; tools e diffs são do ORION): pensamentos, execução de tools e diffs "superficiais" frente a Claude Code/Hermes. Hoje o card mostra `✔ Edit: calc.py · 0.0s · +1 / -1` e o diff; sem parâmetros do comando, duração útil, saída ao vivo, nem raciocínio em bloco. Requer spec de TUI (próxima sprint de interface), não correção pontual.

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
