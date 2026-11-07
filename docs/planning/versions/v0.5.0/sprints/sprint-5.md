# Sprint — v0.5.0 Sprint 5: Extensibilidade & MCP Completo

> **Status:** 📋 Planejando  
> **Versão Relacionada:** v0.5.0  
> **Responsável / Agente:** Daniel Dev & Claude (via ORION)  
> **Data de Início:** —  
> **Data de Conclusão:** —  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Configuração hierárquica, regras de permissão declarativas, hooks, comandos custom e MCP completo.
* **Dependências Prévias:** Sprint 4.
* **Entregável Verificável:** hook que bloqueia tool, regra `deny` que vence `allow`, MCP HTTP/OAuth com resources e prompts.

---

## 2. Contexto de Engenharia

* **Por que existe:** configuração hoje é `~/.orion/config.json` plano; "sempre permitir" vive só em RAM; não há hooks, plugins nem comandos de usuário; MCP só stdio/SSE sem OAuth, resources ou prompts.

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Antes | Depois |
| :--- | :--- | :--- |
| **Settings** | Um JSON | user → projeto → local, com precedência |
| **Permissões** | Níveis PEP fixos | + regras allow/deny/ask por padrão, persistentes |
| **Hooks** | Nenhum | PreToolUse, PostToolUse, UserPromptSubmit, Stop, SessionStart/End, PreCompact, Notification |
| **MCP** | stdio, SSE | + streamable HTTP, headers, OAuth (PKCE), resources, prompts, `list_changed`, reconexão |

---

## 4. Escopo da Sprint

### ✅ No Escopo
- [ ] `settings/` com merge e validação; `.orion/settings.local.json` fora do git.
- [ ] Regras declarativas integradas ao PEP (deny > allow; nuclear nunca contornável).
- [ ] `hooks/` (shell; exit code 2 bloqueia; auditados).
- [ ] Comandos custom `.md` com argumentos; `/skills`; plugin mínimo.
- [ ] MCP: HTTP, OAuth, resources (`@server:recurso`), prompts como slash commands, reconexão, `/mcp add|remove|auth`.

### 🚫 Fora de Escopo
- Marketplace de plugins.

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/settings/ hooks/ plugins/          [novo]
src/orion/governance/{pep,permissions}.py    [mod]
src/orion/mcp/{client,transports,adapter}.py [mod]
src/orion/tui/commands/registry.py           [mod]
tests/unit/test_settings.py test_hooks.py test_mcp_http_oauth.py
```

---

## 6. Contratos de Código & Tipagem

```python
class PermissionRule(BaseModel):
    effect: Literal["allow", "deny", "ask"]
    tool: str              # ex.: "run_command", "mcp__srv__tool"
    pattern: str | None    # ex.: "git status:*"

class HookResult(BaseModel):
    blocked: bool
    message: str | None
```

---

## 7. Estratégia de Implementação

1. Settings e regras no PEP.
2. Hooks e auditoria.
3. Comandos custom e plugin mínimo.
4. MCP HTTP/OAuth, depois resources/prompts e reconexão.

---

## 8. Testes & Critérios de Aceite (DoD)

- Precedência de settings; deny vence allow; hook bloqueante; token OAuth em arquivo 0600; servidor MCP falso HTTP/OAuth.
- [ ] mypy/ruff limpos; cobertura ≥ 85%; `.claudex/progress.md` atualizado.

---

## 9. Critérios de Parada

1. Qualquer regra ou hook capaz de contornar o PEP ou o step-up nuclear.
2. Armazenamento de segredo fora de `~/.orion/` com permissão adequada.
