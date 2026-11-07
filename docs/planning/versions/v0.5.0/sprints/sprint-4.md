# Sprint — v0.5.0 Sprint 4: Paridade de Ferramentas (Portão de Dogfooding)

> **Status:** ✅ Implementada (portão de dogfooding aguardando execução — ver `dogfooding-gate.md`)  
> **Versão Relacionada:** v0.5.0  
> **Responsável / Agente:** Daniel Dev & Claude  
> **Data de Início:** 2026-11-07  
> **Data de Conclusão:** 2026-11-07 (portão pendente)  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Completar o conjunto de ferramentas necessário para programar de verdade pelo ORION.
* **Dependências Prévias:** Sprints 1–3.
* **Entregável Verificável:** o ORION + Claude corrige um bug real do repo (com teste e commit via PEP) sem intervenção do Claude Code.

---

## 2. Contexto de Engenharia

* **Por que existe:** faltam web, glob/grep dedicados, leitura com offset/imagens/PDF, todo, ask_user, plan mode como tool, bash em background.
* **Encaixe:** é o portão para desenvolver as Sprints 5–8 usando o próprio ORION.

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Antes | Depois |
| :--- | :--- | :--- |
| **Leitura** | `read_file` simples | offset/limit, numeração, imagem, PDF |
| **Busca** | `search_files` | + `glob`, `grep` (ripgrep quando houver) |
| **Web** | Nenhuma | `web_fetch`, `web_search` (LEVEL_2, allowlist, anti-injection) |
| **Fluxo** | Sem tasks | `todo_write`, `ask_user`, plan mode |
| **Shell** | Só síncrono | background, `bash_output`, `kill_shell` |

---

## 4. Escopo da Sprint

### ✅ No Escopo
- [x] `read_file` avançado; `edit_file` com `replace_all`.
- [x] `glob`, `grep`, `web_fetch`, `web_search`, `notebook_edit`.
- [x] `todo_write` renderizado na TUI; `ask_user` via modal; `enter/exit_plan_mode` com aprovação.
- [x] Shell em background com monitor de saída.
- [x] Anexo de imagens via `@arquivo.png` (colar da área de transferência: adiado).
- [x] Roteiro documentado do portão (`dogfooding-gate.md`).
- [ ] Execução do portão pelo Senhor (exige chave real).

### 🚫 Fora de Escopo
- Subagents (Sprint 6), hooks/regras (Sprint 5).

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/runtime/tools/{read_file,edit_file,glob,grep,web_fetch,web_search,todo_write,ask_user,plan_mode,notebook_edit,run_command,bash_output,kill_shell}.py
src/orion/governance/permissions.py
src/orion/tui/{modal,panels,session}.py
tests/unit/test_tools_*.py
docs/planning/versions/v0.5.0/dogfooding-gate.md [novo]
```

---

## 6. Contratos de Código & Tipagem
Todas as tools seguem o contrato `BaseTool` da Sprint 2 (`input_schema`, `read_only`, nível PEP declarado).

---

## 7. Estratégia de Implementação

1. Leitura/edição/busca.
2. Web com limites e proteção contra injeção.
3. Todo, ask_user, plan mode.
4. Shell em background.
5. Roteiro de dogfooding e execução.

---

## 8. Testes & Critérios de Aceite (DoD)

- Cada tool: caso feliz, parâmetro inválido, limite de saída, nível PEP correto.
- Web: domínio fora da allowlist negado; conteúdo hostil não vira instrução.
- **Portão:** tarefa real concluída pelo ORION em modo `manual`.
- [x] mypy/ruff limpos; cobertura ≥ 85%; `.claudex/progress.md` atualizado.

---

## 9. Critérios de Parada

1. Falha do portão de dogfooding: não avançar para a Sprint 5 usando o ORION; continuar pelo Claude Code e corrigir.
2. Tool nova sem nível PEP definido.

---

## 10. Entregue além do escopo original (pedido do Senhor, pré-dogfooding)
- **Startup limpo:** o stderr dos servidores MCP (`uvx`/`npx`/serena) ia direto para o terminal porque `stdio_client` usa `sys.stderr` por padrão; agora vai para `~/.orion/logs/mcp-<servidor>.log`. A CLI instala handler de arquivo (`~/.orion/logs/orion-agent.log`), eliminando o `lastResort` do logging no stderr.
- **Tela cheia:** a CLI limpa o terminal no boot e `dock_to_bottom` ancora o prompt no rodapé (só em TTY).

## 11. Decisões
- `read_file` numera linhas por padrão (`N→`; `numbered=false` devolve o texto cru) e lê 2000 linhas por chamada; imagens viram bloco `image` no `tool_result` (`Observation.image`, nunca serializado/logado); PDF via `pdftotext` (poppler), sem nova dependência.
- Web: allowlist (defaults + `~/.orion/web_allowlist.json`), IP não público bloqueado a cada salto de redirect (SSRF), só texto, 2 MB, e trechos que imitam instruções são removidos e o resultado é rotulado como conteúdo não confiável.
- Tools de modal (`ask_user`, `enter/exit_plan_mode`) são LEVEL_0 e `SERIAL_TOOLS`: nunca executam em paralelo. A saída do plano depende do modal de aprovação; sem TTY, a resposta é "não".
- Shell em background usa `subprocess.Popen` + arquivo de log em `~/.orion/shells/` (cada turno da CLI roda num `asyncio.run` próprio); todos morrem ao sair (`atexit`).
- `mypy`: override `disable_error_code=["override"]` em `orion.runtime.tools.*` (o contrato `run(**params)` é validado por JSON Schema).
