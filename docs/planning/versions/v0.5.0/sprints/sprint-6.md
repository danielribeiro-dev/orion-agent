# Sprint — v0.5.0 Sprint 6: Subagents & Tasks

> **Status:** 🟡 6A implementada (2026-11-09) · 6B pendente  
> **Versão Relacionada:** v0.5.0  
> **Responsável / Agente:** Daniel Dev & Claude (via ORION / Claude Code)  
> **Data de Início:** 2026-11-09  
> **Data de Conclusão:** —  
> **Estudo de base:** [`../sprint-6-study.md`](../sprint-6-study.md)

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Delegar trabalho a subagents com contexto isolado, em paralelo e em segundo plano, **sem nunca escalar privilégio**, com orçamento verificável e **sem dependência de um provedor específico**.
* **Dependências Prévias:** Sprints 2, 3, 5.
* **Entregável Verificável:** a sessão principal dispara vários subagents, recebe resumos curtos com referência ao resultado completo e notificações de término; custo por agente visível; nenhum filho executa algo que o pai não poderia.
* **Entrega em dois commits:** **6A** (núcleo foreground, seguro e medido) e **6B** (background, tasks, worktree, `/loop`). Cada commit com `ruff`, `mypy` e cobertura verdes.

### Decisões do Senhor (congeladas)
1. Dividir em **6A e 6B**.
2. Background por **loop asyncio em thread dedicada** (o REPL roda `asyncio.run` por turno e destrói o loop); o runner é reaproveitado pelo daemon na Sprint 7.
3. O núcleo de agentes é **agnóstico de provedor** e depende de portas (ADR-031).

### Princípios de desenho (derivados do estudo)
1. Subagent serve para **isolar contexto volumoso**, não para paralelizar por padrão. Código acoplado fica no agente principal. O pai recebe de 1 a 2 mil tokens.
2. **Tetos no código**, nunca só no prompt: concorrência, profundidade, turnos, tempo e USD.
3. **Privilégio só diminui.** Sem humano para responder, **nega**.
4. **Falhar fechado:** isolamento ou tier exigido que não existe = a task falha explicando; nunca degrada em silêncio.
5. **Resultado por referência:** o completo vai para disco (`ref://`), sobrevive à compactação do pai.
6. **Zero token enquanto espera:** término chega por evento, nunca por polling com LLM.

---

## 2. Contexto de Engenharia

* **Por que existe:** não há subagents nem tasks; `/review` é prompt fixo (`tui/commands/cognitive.py:60`) e `/loop` **não existe**. Subagents economizam contexto e tokens (exploração em modelo barato) e liberam o Senhor para trabalhar enquanto o ORION faz o resto.
* **Fatos do código que condicionam o desenho (verificados):**
  - `ReActEngine` é instanciável N vezes: tudo é injetado (`core/engine.py:223-255`); `llm` é uma callable `async (system, messages, tools) -> ModelTurn`. Cancelamento fecha `tool_use` pendentes (`engine.py:421-431`). `CURRENT_ACTION_ID` é `ContextVar` (seguro com `create_task`; exige `copy_context` em thread/executor).
  - Uma tool só roda em paralelo se `runtime.is_read_only` (nível ≤ 1 e fora de `SERIAL_TOOLS`); tool sem entrada em `TOOL_LEVELS` vira LEVEL_3 (`governance/permissions.py:37-114`).
  - `PolicyEnforcementPoint`: `interactive` só nega **escalada** (`pep.py:557`), não o `ask` comum; `set_interactive` nunca é chamado. Não há teto de privilégio nem `agent_id` na auditoria. `trust_ledger` não é passado ao PEP da sessão.
  - `AgentSession._llm` (`tui/session.py:738-776`) acopla renderer, status bar, router, contadores e **`breaker.set_intentional_lite_mode` a cada chamada** (um filho em tier barato desarmaria o safe-holding do pai).
  - `BudgetGuard` só tem teto diário global, checado antes de cada chamada (TOCTOU com paralelismo). O ledger tem `task_id` (preenchido com `session_id`) e **não tem origem nem agente**.
  - Tiers `FAST/BALANCED/HEAVY` e `ModelRouter.tier_model` já existem (`gateway/router.py:82`).
  - `cli.py:183-190`: `asyncio.run` por turno. `ShellManager` usa `Popen` + arquivo por isso, sem notificação de término e com `log_path` que colide entre instâncias (`shells.py:56`).
  - Rich admite um único `Live`; filhos não podem usar o `StreamRenderer` do pai nem o modal de confirmação.
  - `JsonlSessionStore` e `FactsStore` não têm lock. `_DYNAMIC_LEVELS`/`TOOL_LEVELS` são globais mutáveis. `run_command` aceita `cwd`/`env` livres e o PEP só valida `path`.
  - `tests/unit/test_slash_commands.py:45-49` fixa o catálogo em 26 comandos.

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Antes | Depois |
| :--- | :--- | :--- |
| **Delegação** | Inexistente | Tool `task` com tipos embutidos e custom (`.orion/agents/*.md`) |
| **Execução** | Sequencial | 6A: paralela no turno; 6B: background com notificação |
| **Privilégio** | — | Teto do pai: interseção de tools, `min` de modo, união de `deny/ask`, sem humano = nega |
| **Orçamento** | Diário global | Por agente + agregado por chamada + global, com reserva antecipada |
| **Medição** | `task_id` ambíguo | `origin` e `agent_id` no ledger e na auditoria; custo de filhos em `/cost` |
| **Modelos** | Tier mapeado a IDs fixos | Tiers por capacidade, lista ordenada de candidatos, sem downgrade silencioso |
| **Isolamento** | — | Contexto isolado; worktree git opcional que falha fechado |
| **Comandos** | `/review` fixo; sem `/loop` | `/agents`, `/tasks`, `/loop`, `/review` sobre subagent |

---

## 4. Escopo da Sprint

### ✅ No Escopo — Commit 6A (núcleo foreground)
- [x] `agents/definitions.py`: `AgentDefinition` versionado; carregamento de `.md` com frontmatter de `.orion/agents/`, `~/.orion/agents/` e `agents_dir` de plugin (precedência projeto > usuário > plugin, como os comandos custom). Agente de projeto **não confiável** só pode **restringir** (padrão `restricted()` do TOFU, ADR-023). Leitor também aceita `.claude/agents/*.md` (campos desconhecidos ignorados com aviso).
- [x] Tipos embutidos: `explore` (read-only, tier fast), `plan` (read-only), `general-purpose`, `code-review`.
- [x] `agents/runner.py`: engine isolado por filho (bus, `session_id`, transcript em arquivo próprio, `AutoCompactor`, PEP e `HookRunner` próprios); system mínimo (regras base + prompt do agente); sem identidade, manifest, memória, skills ou MCP por padrão.
- [x] `make_llm(tier, on_usage)` extraído de `AgentSession._llm`, **sem tocar** em breaker, renderer, status bar nem contadores da sessão.
- [x] **Teto de privilégio no PEP** (`ceiling`/`parent_pep`): modo do filho `min(pai, filho)`; `deny` e `ask` do pai unidos; `allow` não herdado; `interactive=False` passa a negar **todo** `ask`; filho nunca grava regra (`append_local_rule`) nem usa trust ledger; wrapper de runtime filtra `tool_specs/supports/execute` (interseção).
- [x] Filho **nunca** recebe `task`, `ask_user`, `enter/exit_plan_mode`, `record_decision`, `memorize`, `deprecate_fact` (profundidade 1; configurável com teto).
- [x] Tool `task` (`runtime/tools/task.py`) com nível PEP definido (≤ 1, paralela) e parâmetros `agent`, `goal`, `context`, `output_schema?`, `tasks?` (lote).
- [x] Orçamento: `AgentBudget` + `AggregateBudget`, reserva antecipada (estimativa por `max_tokens` × preço do `CostCalculator`); estouro devolve parcial marcado e retomável.
- [x] Ledger: colunas `origin` e `agent_id` (migração `ALTER`, padrão de `cache_write_tokens`), soma por agente; auditoria com `agent_id`; eventos `SubagentStarted/Completed`; hooks `SubagentStart/SubagentStop` (só bloqueiam, ADR-024).
- [x] Router: `models.tiers` (lista ordenada de candidatos por tier) e *capability flags* (ADR-031).
- [x] TUI: `/agents` (módulo novo em `_MODULES`, `OFFICIAL_SLASH_COMMANDS` e teste de contagem); progresso compacto por filho (uma linha, sem `Live` próprio); custo dos filhos em `/cost` e na status bar; `/review` reescrito sobre o agente `code-review`.
- [x] Mutações de filhos entram no `ChangeTracker` (`/undo`, `/rewind`) com `agent_id`.

### ✅ No Escopo — Commit 6B (background, tasks, worktree, loop)
- [ ] `agents/loop_thread.py` + `ExecutorPort`: loop persistente em thread, `copy_context` ao despachar, fila thread-safe de notificações drenada antes de cada prompt e na toolbar.
- [ ] `agents/tasks.py` + `TaskStorePort` (SQLite parametrizado em `~/.orion/tasks.db`): id, dono, status, tier/modelo efetivo, ref de saída; sobrevive a reinício. Tools `task_create/list/get/stop` e `/tasks` (lista também os shells do `ShellManager`, com `log_path` por instância corrigido).
- [ ] `Ctrl+C` cancela o turno, **não** as tasks; `/tasks stop` e cascata ao encerrar a sessão.
- [ ] Mensagens pai→filho (`send_message`: fila de entrada lida entre turnos do filho); retomada de filho parcial com o mesmo modelo.
- [ ] Worktree (`isolation: worktree`) via `WorkspacePort`: `git worktree` temporário, `WorkspaceScope` próprio, `cwd` forçado e **validado no PEP** para `run_command/glob/grep`, limpeza automática se sem mudanças; **falha fechada** fora de repositório git.
- [ ] `/loop` (intervalo fixo ou dinâmico) sobre tasks: disparo = subagent de orçamento limitado, gancho `TriagePort` (determinístico primeiro; tier fast só se inconclusivo, `max_tokens` mínimo), expiração padrão de 7 dias, teto de disparos, origem `loop`.

### 🚫 Fora de Escopo
- Agentes que se auto-criam (v1.5.0), agent teams (filhos conversando entre si), sandbox (v1.5.0).
- Persistência durável de `/loop` e cron real (Sprint 7); notificação desktop/Telegram (Sprint 7).
- Escrita de memória por filho e propostas pendentes (Memória Viva, ADR-027).

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/agents/
  ports.py            [novo]  LLMPort, ExecutorPort, TaskStorePort, NotifierPort, WorkspacePort, TriagePort
  definitions.py      [novo]  AgentDefinition, loader, embutidos
  runner.py           [novo]  AgentRunner (engine isolado, PEP filho, orçamento)
  budget.py           [novo]  AgentBudget, AggregateBudget
  tasks.py            [novo]  6B  TaskRecord, TaskManager, SqliteTaskStore
  loop_thread.py      [novo]  6B  ThreadExecutor + fila de notificações
  worktree.py         [novo]  6B  GitWorktreeWorkspace
  loops.py            [novo]  6B  LoopScheduler em processo
src/orion/runtime/tools/task.py            [novo]  tool task (+ task_* na 6B)
src/orion/tui/commands/agents.py           [novo]  /agents, /tasks, /loop
src/orion/core/engine.py, events.py        [mod]   agent_id/parent_id/origin nos eventos
src/orion/governance/{pep,permissions,audit}.py [mod] teto, interactive nega ask, agent_id
src/orion/gateway/{ledger,budget,router,models}.py [mod] origin/agent_id, tiers, capabilities
src/orion/tui/session.py                   [mod]   extrair make_llm, somar custo dos filhos
src/orion/tui/commands/{registry,cognitive}.py, completer.py [mod]
src/orion/settings/models.py               [mod]   hooks SubagentStart/Stop, chaves agents.* e models.tiers
src/orion/runtime/tools/shells.py          [mod]   6B  log_path por instância
tests/unit/test_subagents.py test_agent_privilege.py test_agent_budget.py test_agent_definitions.py test_tasks.py test_worktree.py test_loop.py
```

---

## 6. Contratos de Código & Tipagem

```python
# agents/ports.py — o núcleo de agentes só conhece estas portas
class LLMPort(Protocol):                      # = callable atual do engine
    async def __call__(self, system: list[SystemBlock], messages: list[Message],
                       tools: list[ToolSpec]) -> ModelTurn: ...

class ExecutorPort(Protocol):                 # 6A foreground; 6B thread; Sprint 7 daemon; futuro remoto
    def submit(self, coro_factory: Callable[[], Awaitable[AgentResult]], *, agent_id: str) -> TaskHandle: ...
    async def cancel(self, agent_id: str) -> None: ...

class TaskStorePort(Protocol):                # 6B SQLite; Sprint 7 reaproveita o esquema
    def upsert(self, rec: TaskRecord) -> None: ...
    def get(self, task_id: str) -> TaskRecord | None: ...
    def list(self, *, status: TaskStatus | None = None) -> list[TaskRecord]: ...

class NotifierPort(Protocol):                 # 6B fila em processo; Sprint 7 notify-send/Telegram
    def notify(self, event: AgentEventEnvelope) -> None: ...

class WorkspacePort(Protocol):                # none | worktree; extensível a sandbox (v1.5.0)
    async def prepare(self, agent_id: str) -> WorkspaceScope: ...
    async def release(self, agent_id: str, *, keep_if_changed: bool) -> WorkspaceOutcome: ...

class TriagePort(Protocol):                   # determinístico primeiro; modelo barato só se inconclusivo
    async def should_wake(self, ctx: TriageContext) -> TriageDecision: ...
```

```python
class AgentDefinition(BaseModel):
    schema_version: Literal[1] = 1
    name: str
    description: str
    prompt: str                                       # corpo do .md
    tools: list[str] | None = None                    # None = herda; nunca acima do pai
    disallowed_tools: list[str] = []
    model_tier: Literal["fast", "balanced", "heavy"] = "balanced"
    model_profile: str | None = None                  # nome em settings; ID concreto proibido (ver ADR-031)
    max_turns: int = 20
    budget_usd: float | None = None
    timeout_s: int | None = None
    isolation: Literal["none", "worktree"] = "none"   # enum extensível (sandbox na v1.5.0)
    skills: list[str] = []
    memory: Literal["none", "read"] | str = "none"    # "scoped:<escopo>" reservado à Memória Viva
    result_max_tokens: int = 1500
    source: Literal["builtin", "user", "project", "plugin"] = "user"

class AgentEventEnvelope(BaseModel):                  # JSON-serializável (IPC da Sprint 7, desktop, voz)
    agent_id: str
    parent_id: str | None
    session_id: str
    origin: Literal["user", "subagent", "loop", "cron", "daemon"]
    kind: str
    payload: dict[str, Any]

class AgentResult(BaseModel):
    agent_id: str
    status: Literal["ok", "partial_budget", "partial_turns", "partial_timeout", "cancelled", "error", "schema_invalid"]
    summary: str                    # curto, limitado por result_max_tokens
    ref: str                        # ref://agents/<id>/result.md (completo, em ~/.orion/agents/)
    model_used: str                 # modelo efetivo gravado; retomada reutiliza
    usage: UsageTotals              # tokens, cache read/write, custo USD
    resumable: bool
```

Frontmatter de exemplo (`.orion/agents/auditor.md`):

```markdown
---
schema_version: 1
name: auditor
description: Audita um diretório em busca de TODOs e código morto (somente leitura)
tools: [read_file, glob, grep]
model_tier: fast
max_turns: 12
budget_usd: 0.05
---
Você audita o código solicitado e devolve uma lista curta, com caminho:linha. Não modifique nada.
```

Configuração (`settings.json`, camadas ADR-023; camada de projeto só vale se confiável):

```json
{
  "agents": {"max_concurrent": 4, "max_depth": 1, "default_max_turns": 20, "result_max_tokens": 1500},
  "models": {"tiers": {"fast": ["<candidatos em ordem>"], "balanced": [], "heavy": []},
             "profiles": {"barato": {"tier": "fast"}}}
}
```

---

## 7. Estratégia de Implementação

**6A**
1. `ports.py`, `definitions.py` e loader (com testes de precedência/TOFU), sem tocar o runtime.
2. Extrair `make_llm` da sessão (sem alterar comportamento; teste de regressão do breaker).
3. Ceiling no PEP + wrapper de runtime filtrado + `interactive=False` negando todo `ask`.
4. `AgentRunner` + `AgentBudget`/`AggregateBudget` com reserva; resultado em disco com `ref://`.
5. Tool `task` (nível PEP definido), eventos/hook/auditoria/ledger com `agent_id` e `origin`.
6. `/agents`, `/review` sobre subagent, custo somado, `ChangeTracker`.

**6B**
1. `ThreadExecutor` + fila de notificações + drenagem no REPL; `TaskStore` SQLite.
2. Tools `task_*`, `/tasks`, cancelamento (turno ≠ task), correção do `log_path` dos shells.
3. `send_message` e retomada.
4. `GitWorktreeWorkspace` com `cwd` validado no PEP.
5. `/loop` em processo com `TriagePort`.

---

## 8. Testes & Critérios de Aceite (DoD)

Todos com `ScriptedLLM`/`ScriptedProvider` (custo zero; nenhuma chamada paga em teste automático, `ORION_LIVE=1` para o live).

**6A**
- N filhos em paralelo na mesma volta (leituras em lote, `task` paralela); resultados na ordem dos `tool_use`.
- Cancelamento em cascata: cancelar o pai cancela os filhos e fecha os `tool_use` pendentes.
- Estouro de orçamento por agente e agregado: resultado `partial_budget`, resumível; reserva impede ultrapassar o teto com chamadas paralelas.
- Escalada de privilégio negada: filho sem tool que o pai não tem; `min(modo)`; `deny/ask` do pai valem no filho; `allow` não herdado; `ask` com `interactive=False` é negado; filho não grava regra; filho sem `task`, `ask_user`, plan mode, memória.
- Breaker intacto: `intentional_lite_mode` não muda por causa de um filho.
- Agente de projeto não confiável não amplia tools, modelo nem orçamento.
- Resultado do filho sobrevive à compactação do pai (lido via `ref://`).
- Tier sem candidato adequado: tools mutantes falham explicando (sem downgrade silencioso); read-only pode cair para o candidato local.
- Ledger/auditoria com `origin` e `agent_id`; `/cost` soma filhos; migração `ALTER` idempotente.
- Catálogo de comandos atualizado (contagem do teste).

**6B**
- Notificação de término entregue entre turnos sem nenhuma chamada ao provider enquanto aguarda.
- `Ctrl+C` cancela o turno mas não as tasks; `/tasks stop` cancela; encerrar a sessão cancela tudo.
- Estado das tasks persiste e é relido após reinício (tasks não terminadas viram `interrupted`).
- `send_message` chega entre turnos do filho; retomada usa o mesmo modelo gravado.
- Worktree: isola escrita, `cwd` fora é negado pelo PEP, limpa se sem mudanças, **falha fechada** fora de git.
- `/loop`: expiração, teto de disparos, triagem determinística evita acordar o modelo, origem `loop` no ledger.

- [ ] `ruff` e `mypy` sem erros novos nos arquivos tocados (backlog pré-existente: 26 mypy); cobertura global ≥ 85%; `tests/e2e/test_security_audit.py` verde; `.claudex/progress.md`, `active_context.md` e `VERSION.md` atualizados.
- [ ] Validação manual em TTY real (modal, `/agents`, `/tasks`, notificação) e, só com `ORION_LIVE=1` e teto no `BudgetGuard`, uma rodada live no `explore`.

---

## 8.1 Registro de implementação da 6A (2026-11-09)

Desvios e decisões tomadas na execução (a spec congelada continua válida):

* **Porta extra:** `ModelGatewayPort` (resolve tier→modelo e entrega o `llm` isolado) completa as 6 portas da spec; `LLMPort` usa a assinatura real do engine (`system: str`), não `list[SystemBlock]`.
* **`make_llm`:** em vez de um método da sessão, o código comum virou `gateway/agent_gateway.py` (`build_llm_request`, `consume_stream`, `AgentGateway`); `AgentSession._llm` passou a usá-lo (comportamento idêntico, coberto por `test_agent_session`).
* **Nuclear sem humano:** com `interactive=False` o desafio do SO **não abre**; o comando nuclear é negado (consistente com "sem humano = nega" e com o critério de parada 3).
* **`task` é LEVEL_1:** delegar não muda nada; o risco real é decidido a cada tool do filho sob o teto do pai.
* **Reserva = pior caso:** prompt estimado + `max_tokens` (8192 por chamada de filho). Com tarifa alta e orçamento baixo, a reserva pode impedir uma chamada que custaria menos; é a troca deliberada por teto verificável.
* **Mutante exige tier ≥ balanced:** agente com tools mutantes e `model_tier: fast` falha explicando (não sobe de tier em silêncio).
* **`/review`:** o diff vai como `context` do subagent `code-review` (somente leitura); o resumo entra no histórico do pai com a `ref://`.
* **Fora desta etapa, na 6B:** `ThreadExecutor`, `tasks.db`, `/tasks`, `/loop`, worktree (`isolation: worktree` já **falha fechado** na 6A), `send_message` e `Ctrl+C` ≠ tasks.

---

## 9. Critérios de Parada

1. Subagent executando algo que o pai não poderia executar.
2. Custo agregado sem teto verificável.
3. Qualquer `ask` interativo originado em filho.
4. Filho alterando o estado do circuit breaker do pai.
5. Chamada ao provider enquanto apenas se aguarda uma task.
6. Downgrade silencioso de modelo em agente com tools mutantes.
7. Isolamento pedido (worktree) que cai para o workspace compartilhado.
