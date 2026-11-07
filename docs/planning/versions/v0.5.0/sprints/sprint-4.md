# Sprint — v0.5.0 Sprint 4: Paridade de Ferramentas (Portão de Dogfooding)

> **Status:** 📋 Planejando  
> **Versão Relacionada:** v0.5.0  
> **Responsável / Agente:** Daniel Dev & Claude  
> **Data de Início:** —  
> **Data de Conclusão:** —  

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
- [ ] `read_file` avançado; `edit_file` com `replace_all`.
- [ ] `glob`, `grep`, `web_fetch`, `web_search`, `notebook_edit`.
- [ ] `todo_write` renderizado na TUI; `ask_user` via modal; `enter/exit_plan_mode` com aprovação.
- [ ] Shell em background com monitor de saída.
- [ ] Anexo de imagens (`@arquivo.png`/colar).
- [ ] Roteiro documentado do portão de dogfooding e execução dele.

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
- [ ] mypy/ruff limpos; cobertura ≥ 85%; `.claudex/progress.md` atualizado.

---

## 9. Critérios de Parada

1. Falha do portão de dogfooding: não avançar para a Sprint 5 usando o ORION; continuar pelo Claude Code e corrigir.
2. Tool nova sem nível PEP definido.
