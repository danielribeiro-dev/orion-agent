# Sprint — v0.5.0 Sprint 5: Extensibilidade & MCP Completo

> **Status:** 📋 Spec detalhada (aguardando comando de início)  
> **Versão Relacionada:** v0.5.0  
> **Responsável / Agente:** Daniel Dev & Claude Code (o portão de dogfooding segue pendente)  
> **Data de Início:** —  
> **Data de Conclusão:** —  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Configuração hierárquica, regras de permissão declarativas, hooks, comandos custom, plugin mínimo e MCP completo.
* **Dependências Prévias:** Sprint 4.
* **Entregável Verificável:** hook que bloqueia tool, regra `deny` que vence `allow`, MCP HTTP/OAuth com resources e prompts.
* **Entrega em dois commits:** **5A** (settings, regras, hooks, comandos custom, plugin) e **5B** (MCP completo). Cada commit com `ruff`, `mypy` e cobertura verdes.

### Decisões do Senhor (congeladas)
1. Um sprint, dois commits.
2. Settings de projeto exigem **confiança na primeira vez** (trust-on-first-use): hooks, regras `allow` e `mode` vindos do projeto só valem depois que o Senhor confia na pasta (substitui a decisão anterior de "confiável por padrão").
3. Formato `settings.json` estilo Claude Code.
4. Hooks **só bloqueiam ou deixam seguir**; nunca aprovam nem alteram parâmetros.
5. **Perguntar em vez de bloquear:** o PEP deixa de ter bloqueios estruturais por lista para sudo e para caminhos fora do workspace; ambos passam a **pedir confirmação** ao Senhor com o comando real na tela. Só continuam como bloqueio duro o desafio nuclear do SO e o safe-holding do circuit breaker.

---

## 2. Contexto de Engenharia

* **Por que existe:** a configuração é `~/.orion/config.json` plano, lido ad hoc em `tui/session.py` (`_load_settings`, `save_settings`; só 4 chaves). "Sempre permitir" vive em RAM (`session.always_allowed`). Não há hooks, plugins nem comandos de usuário. O MCP só tem stdio/SSE, sem OAuth, resources, prompts, reconexão ou `add/remove`.
* **Fatos do código que condicionam o desenho:**
  - `PolicyEnforcementPoint.evaluate` roda em `runtime/local_provider.py::execute`, único caminho de execução (`execute_direct` é só de teste). Ordem: sudo, escopo, safe-holding, nuclear, `_gate`/`_ask_user`.
  - O modo PLAN depende de `SUPERVISED` sempre cair em `_ask_user` para devolver `Rejection`.
  - O `Action.event_id` do engine difere do recriado no runtime, então a auditoria não correlaciona com `ActionEmitted`.
  - Negações por sudo/escopo não são auditadas; `"pending"` nunca é fechado.
  - O SDK instalado é `mcp 2.3.0` (`httpx2`, `streamable_http_client`, `OAuthClientProvider` com PKCE S256), mas o `pyproject.toml` declara `mcp>=1.0.0`.
  - O catálogo de slash commands está duplicado (`OFFICIAL_SLASH_COMMANDS` em `tui/completer.py` e o registry); `/help` itera o estático.

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Antes | Depois |
| :--- | :--- | :--- |
| **Settings** | Um JSON com 4 chaves | user → projeto → local, com precedência e validação |
| **Permissões** | Níveis PEP fixos; "sempre permitir" em RAM | + regras allow/deny/ask por padrão, persistentes (camada local) |
| **Hooks** | Nenhum | PreToolUse, PostToolUse, UserPromptSubmit, Stop, SessionStart/End, PreCompact, Notification |
| **Comandos** | Catálogo fixo de 25 | + `.md` custom com argumentos, `/skills`, plugin mínimo; `/help` e completer derivam do registry |
| **MCP** | stdio, SSE | + streamable HTTP, headers, OAuth (PKCE), resources, prompts, `list_changed`, reconexão, `/mcp add\|remove\|auth` |
| **Auditoria** | Lacunas (sudo/escopo, `pending`) | `decision_source`, negações completas, resultado fechado, `action_id` correlacionado |

---

## 4. Escopo da Sprint

### ✅ No Escopo — Commit 5A
- [ ] `settings/` com merge e validação; `.orion/settings.local.json` fora do git, 0600.
- [ ] Regras declarativas integradas ao PEP (deny > ask > allow; nuclear, sudo e escopo nunca contornáveis).
- [ ] "Sempre permitir" persistente como regra `allow` na camada local (nunca para nuclear nem sudo).
- [ ] Confiança na primeira vez para settings/hooks de projeto (`~/.orion/trusted_projects.json`, hash do arquivo, 0600).
- [ ] sudo e caminhos fora do workspace: de bloqueio para pergunta com motivo; sem humano, negar.
- [ ] `hooks/` (shell; exit 2 bloqueia; auditados).
- [ ] Comandos custom `.md` com `$ARGUMENTS`/`$1..$n`; `/skills`; plugin mínimo.
- [ ] `/help` e completer derivados do registry.
- [ ] Lacunas de auditoria fechadas.

### ✅ No Escopo — Commit 5B
- [ ] MCP: streamable HTTP, headers com `${VAR}`, OAuth PKCE, resources (`@server:recurso`), prompts como slash commands, `list_changed`, reconexão com backoff, `/mcp add|remove|auth|resources|prompts`.

### 🚫 Fora de Escopo
- Marketplace e instalação remota de plugins.
- F-09 (TUI de detalhe): conflita em `session.py`/`completer.py`, fica para sprint própria.
- Hooks que aprovam ou reescrevem parâmetros.

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/settings/{models,loader}.py              [novo]
src/orion/hooks/{runner,events}.py                 [novo]
src/orion/plugins/loader.py                        [novo]
src/orion/governance/rules.py                      [novo]
src/orion/governance/{pep,permissions,audit}.py    [mod]
src/orion/runtime/local_provider.py                [mod]  Pre/PostToolUse antes/depois do PEP
src/orion/tui/{session,cli,completer,prompt}.py    [mod]
src/orion/tui/commands/{registry,mcp,operation}.py [mod]
src/orion/tui/commands/custom.py                   [novo]
src/orion/memory/models.py                         [mod]  SkillMetadata: allowed-tools, argument-hint
src/orion/mcp/oauth.py                             [novo]
src/orion/mcp/{models,transports,client,runner,adapter,spawn_policy}.py [mod]
pyproject.toml                                     [mod]  mcp>=2.3, httpx2
tests/unit/test_settings.py test_permission_rules.py test_hooks.py
tests/unit/test_custom_commands.py test_plugins.py
tests/unit/test_mcp_http_oauth.py test_mcp_resources_prompts.py
tests/e2e/test_security_audit.py                   [mod]  casos de não-bypass
tests/fixtures/echo_mcp_server.py                  [mod]  modo `http <porta>`
```

### Pontos de integração
| Necessidade | Local |
| :--- | :--- |
| PreToolUse / PostToolUse | `local_provider.execute`, antes de `evaluate` (~l.198) e após o dispatch |
| UserPromptSubmit | `session.run_turn`, antes de `_with_mentions` |
| Stop | após `self.history = engine.messages`; erro e cancelamento |
| SessionStart / SessionEnd | fim de `__init__`/`resume()`; `finally` em `run_interactive_repl` (também fecha o MCP) |
| PreCompact | antes de `compact_messages` em `compact` e `_on_autocompact` |
| Notification | `_confirm`, `_ask_user`, `_approve_plan` |
| Geração MCP | `refresh_mcp` troca contagem de servidores por contador de geração |

---

## 6. Contratos de Código & Tipagem

```python
class PermissionRule(BaseModel):
    effect: Literal["allow", "deny", "ask"]
    tool: str              # ex.: "run_command", "mcp__srv__tool", "mcp__srv__*"
    pattern: str | None    # ex.: "git status:*"

class HookResult(BaseModel):
    blocked: bool
    message: str | None

class Settings(BaseModel):                 # extra="ignore" com warning
    model: str | None
    effort: ReasoningEffort | None
    mode: AgentMode | None
    daily_budget_usd: float | None
    permissions: Permissions               # allow/deny/ask: list[str]
    hooks: dict[HookEvent, list[HookSpec]]
    mcp: dict[str, MCPServerConfig]
    env: dict[str, str]

class CustomCommand(BaseSlashCommand):     # registrado via registry.register()
    source: Literal["user", "project", "plugin"]

class TokenStorage(Protocol):              # SDK mcp; impl. em mcp/oauth.py (0600)
    async def get_tokens(self) -> OAuthToken | None: ...
    async def set_tokens(self, t: OAuthToken) -> None: ...
```

### Regras de avaliação (invioláveis)
1. Ordem do PEP: **safe-holding** e **nuclear** (bloqueio duro, desafio do SO) rodam primeiro e permanecem intactos. Depois, **sudo** e **fora do workspace** viram *escalada com confirmação*: `ActionDenied` só ocorre se o Senhor recusar ou se não houver interação possível (item 7).
2. `deny` casa: `log_denied(reason="rule_deny:<regra>")` e `ActionDenied`. Precedência **deny > ask > allow**.
3. `allow` só dispensa a pergunta em LEVEL_2, e **nunca** em `SUPERVISED`/PLAN.
4. `ask` força `_ask_user` mesmo em `WORKSPACE_AUTO`/`FULLY_AUTO` (exceto nuclear, que segue seu gate).
5. Hook: exit 2 bloqueia (stderr volta ao modelo); qualquer outro código segue ao PEP; falha/timeout não bloqueia mas é auditado. Saída de hook é dado não confiável (neutralizar `<<<ORION_`, truncar).
6. Tool desconhecida continua LEVEL_3; regra não rebaixa.
7. **Confirmação de escalada (sudo / fora do workspace):**
   - A pergunta mostra o comando ou caminho exato e o motivo ("usa sudo", "fora do workspace").
   - A aprovação vale **uma vez**: não existe "sempre permitir" para sudo, e regra `allow` não o libera (só o Senhor, na hora). Fora do workspace pode ter `allow` por diretório, só na camada local.
   - O recusar devolve `Rejection` com o motivo ao modelo, que explica ao Senhor e propõe alternativa (em vez de "o sistema me bloqueou").
   - **Sem humano para perguntar** (hooks, subagents, jobs agendados, daemon, modo não interativo): a escalada é **negada**, nunca aprovada por padrão. Vale para as Sprints 6 e 7.
   - Em `FULLY_AUTO` o comportamento atual (sudo liberado) é mantido; nuclear continua exigindo o SO.
   - Toda escalada, aprovada ou recusada, é auditada com `decision_source`.
8. `deny` deixa de ser lista embutida: existe apenas como regra declarada pelo Senhor. Não se tenta mapear comandos maliciosos; o que não é conhecido cai em LEVEL_3 e pergunta.

---

## 7. Estratégia de Implementação

**5A**
1. Settings: modelos, loader por camadas, migração do `config.json`, helper `write_private_json` (escrita atômica 0600).
2. Regras no PEP + persistência do "sempre permitir" + lacunas de auditoria + unificação do `action_id`.
3. Hooks: runner, pontos de integração, auditoria.
4. Registry/completer/`/help` derivados do registry; comandos custom; `/skills`; plugin mínimo.
5. ADR-023 (settings e regras), ADR-024 (hooks), ADR-025 (comandos custom e plugins, afrouxa o ADR-016); atualizar `CLI_AGENT_RULES.md` seção 2. Verde, commit 5A.

**5B**
6. `mcp>=2.3`, `httpx2`; modelos; `open_session` com ramo HTTP, headers e validação de URL por `web_policy.py`.
7. `mcp/oauth.py` (storage 0600, loopback, redirect handler) e `message_handler`.
8. Cliente: paginação, resources/prompts, `add/remove`, reconexão com backoff, `list_changed`; espelho em `runner.py`.
9. Sessão/TUI: geração, tools sintéticas LEVEL_1, prompts como slash commands, `@server:recurso`, `/mcp add|remove|auth|resources|prompts`. Verde, commit 5B.

---

## 8. Testes & Critérios de Aceite (DoD)

- **Settings:** precedência user < projeto < local, merge de listas, migração, arquivo inválido, local 0600.
- **Regras:** deny vence allow; allow não pula pergunta em PLAN/SUPERVISED; allow nunca libera nuclear/sudo/escopo; ask força pergunta em `FULLY_AUTO`; "sempre permitir" persiste na camada local.
- **Hooks:** exit 2 bloqueia; exit 0/1 segue ao PEP; hook não aprova nem altera params; timeout auditado; cada evento dispara no ponto certo; delimitadores forjados neutralizados.
- **Comandos/plugin:** `$ARGUMENTS`/`$1`, projeto vence user, colisão com nativo recusada, namespace de plugin, `/help` e completer listam dinâmicos.
- **MCP:** servidor falso HTTP e OAuth (discovery, register, authorize, token com verificação S256, 401 com `WWW-Authenticate`); token em arquivo 0600 e refresh; headers `${VAR}`; resources, prompts, `list_changed`, reconexão.
- **Confiança de projeto:** primeira abertura pergunta; sem confiança, hooks, `allow` e `mode` do projeto são ignorados e `deny`/`ask` continuam valendo; mudança no arquivo (hash) pede confiança de novo; decisão guardada em `~/.orion/` com 0600.
- **Escalada com pergunta:** `sudo apt update` pergunta com o comando real e executa se aprovado; recusa devolve `Rejection` explicativa; sudo nunca vira "sempre permitir" nem passa por regra `allow`; sem humano (hook, subagent, não interativo) a escalada é negada; auditada. Ajustar os testes atuais de `test_security_audit.py` que esperam `ActionDenied` imediato para sudo e escopo.
- **Segurança (e2e):** regra allow, hook e plugin não contornam o desafio nuclear nem o safe-holding, nem aprovam sudo/escopo sem o Senhor.
- [ ] CA-06 e CA-07 do `VERSION.md` marcados.
- [ ] `ruff check src tests`; `mypy src` sem erros novos (backlog de 26); cobertura ≥ 85%; sem chamadas pagas (`ORION_LIVE`).
- [ ] `.claudex/progress.md`, `active_context.md` e tabela do `VERSION.md` atualizados.

---

## 9. Critérios de Parada

1. Qualquer regra, hook ou plugin capaz de contornar o desafio nuclear, o safe-holding, ou de aprovar sudo/fora do workspace sem o Senhor.
2. Armazenamento de segredo fora de `~/.orion/` ou sem permissão 0600.
3. Qualquer caminho em que a escalada seja aprovada por padrão quando não há humano para perguntar.

### Riscos conhecidos
- **Fadiga de confirmação:** perguntar mais pode levar a aprovar no automático. Mitigação: a pergunta mostra o comando exato e o motivo; sudo nunca é "sempre"; repetições seguras usam o trust ledger existente.
- **Confiança de projeto:** o hash do arquivo é o gatilho; edição por `git pull` pede confiança de novo.
