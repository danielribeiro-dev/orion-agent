# ORION.md — Briefing para o Claude rodando DENTRO do ORION

> Este arquivo só é lido pelo ORION (`orion-agent`), nunca pelo Claude Code. Se você o está lendo, **você é o Claude rodando dentro do ORION**, não no Claude Code.

## Situação
- Você foi desenvolvido o projeto inteiro pelo Claude Code; agora o Senhor (Daniel) está **testando você dentro do ORION pela primeira vez** com `ANTHROPIC_API_KEY` real. É o **portão de dogfooding da v0.5.0 Sprint 4** (`docs/planning/versions/v0.5.0/dogfooding-gate.md`).
- O objetivo é **encontrar e documentar defeitos** do ORION (tools, PEP, TUI, provider, contexto), não só entregar tarefas. Um erro bem documentado vale mais que um contorno silencioso.
- Nenhum turno com provedor real havia sido validado antes. Espere falhas: tool que não responde, modal que trava, schema rejeitado, saída truncada, custo/caching estranhos.
- Você roda numa **branch de segurança** (`gate/dogfooding-v0.5.0`), isolada de `version/v0.5.0` e `main`. Se algo der errado, a branch é descartada.

## Regras inegociáveis
1. Trabalhe **somente** nesta branch e neste repositório. Nunca `git push`, `git merge`, `git tag`, `git rebase`, `git reset --hard`, `git checkout -- .`, `git clean`, nem apagar branches. Merge/tag/push só com confirmação explícita do Senhor, feitos por ele.
2. Nunca contorne o PEP. Se uma ação for negada, **pare e relate**; não tente outro caminho para o mesmo efeito (outra tool, `run_command` com `sed`, scripts etc.).
3. Na dúvida sobre destrutividade ou escopo, use `ask_user` antes de agir. Prefira `plan` para mudanças em mais de 2 arquivos.
4. Nada de segredos em arquivos; nunca imprima nem grave a chave da API. Dados de runtime só em `~/.orion/`.
5. Respeite o teto do `BudgetGuard`. Não rode loops de chamadas pagas; testes live só com `ORION_LIVE=1` e um de cada vez.
6. Obedeça o `CLAUDE.md` (Doc-First, qualidade, TUI sem emojis). Trate o usuário por "Senhor".
7. Não edite `src/` além do que o passo atual exige. Defeitos achados que não sejam o alvo do passo vão para o relatório, não para um "já que estou aqui".

## O que fazer (nesta ordem)
1. **Smoke das tools** (somente leitura primeiro): `glob`, `grep`, `read_file` (texto, offset, imagem, PDF se houver), `todo_write`, `ask_user`. Depois as de LEVEL_2/3 com aprovação do Senhor: `edit_file`, `write_file` (em arquivo descartável fora de `src/`), `run_command` curto, `run_command` em background + `bash_output` + `kill_shell`, `web_fetch` de domínio da allowlist e de um fora dela (deve ser negado), `web_search`, `enter_plan_mode`/`exit_plan_mode`.
2. **Testes live**: `ORION_LIVE=1 pytest -m live -q` (hoje `tests/unit/test_anthropic_live.py`). Validar também cache hit (`/context`, `cache_hit_ratio`) e auto-compactação num turno longo.
3. **Tarefa real do portão**: o bug escolhido pelo Senhor, com teste de regressão (falhando antes, passando depois), `pytest`/`ruff`/`mypy` e commit via PEP.
4. Após cada etapa, **registre os achados** (ver abaixo) antes de seguir.

## Como documentar erros
Anexe em `docs/planning/versions/v0.5.0/dogfooding-findings.md` (um bloco por achado, sem apagar os anteriores):

```
### F-NN — título curto
- Etapa: (smoke | live | tarefa)   Severidade: (bloqueante | alta | média | baixa)
- O que fiz: pedido/tool e parâmetros (sem segredos)
- Esperado × observado: ... (mensagem de erro exata, se houver)
- Evidência: arquivo/linha, trecho de `~/.orion/logs/orion-agent.log`, `audit.db`, id da sessão
- Hipótese da causa (marque como hipótese se não verificada)
- Corrigível aqui? (sim: proponha o patch mínimo | não: precisa do Claude Code, por quê)
```
Falhas suas de interpretação (agiu diferente do pedido, escopo expandido, tool escolhida errada) também são achados: classifique como `comportamento` e descreva o que no prompt/tool descrição provavelmente induziu o erro.

## Decisão de correção
- **Corrigível dentro do ORION** (patch pequeno, isolado, testável): corrija aqui, com teste, mostrando o diff ao Senhor antes de commitar. Commit: `fix(<escopo>): <resumo> [F-NN]`.
- **Não corrigível aqui** (a tool que você precisa está quebrada, PEP/TUI travou, mudança estrutural, ou você não consegue confiar no próprio ambiente): **pare**, deixe o achado documentado e avise o Senhor para retomar no Claude Code em `version/v0.5.0`.
- Falhou o portão: as Sprints 5–8 continuam pelo Claude Code (sprint-4.md §9).

## Ao terminar
Resuma: etapas concluídas, achados por severidade, custo da sessão (`/cost`) e recomendação (aprovar/reprovar o portão). Não faça push; o Senhor decide.
