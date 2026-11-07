# Sprint — v0.5.0 Sprint 6: Subagents & Tasks

> **Status:** 📋 Planejando  
> **Versão Relacionada:** v0.5.0  
> **Responsável / Agente:** Daniel Dev & Claude (via ORION)  
> **Data de Início:** —  
> **Data de Conclusão:** —  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Delegar trabalho a subagents com contexto isolado, em paralelo e em segundo plano, sem escalar privilégio.
* **Dependências Prévias:** Sprints 2, 3, 5.
* **Entregável Verificável:** sessão principal dispara vários subagents, recebe resultados e notificações de término.

---

## 2. Contexto de Engenharia

* **Por que existe:** não há subagents nem tasks; `/review` e `/loop` são prompts fixos. Subagents economizam contexto e tokens (exploração em Haiku).

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Antes | Depois |
| :--- | :--- | :--- |
| **Delegação** | Inexistente | Tool `task` com tipos embutidos e custom (`.orion/agents/*.md`) |
| **Execução** | Sequencial | Paralela e em background com notificação |
| **Orçamento** | Global | Por agente + total (`BudgetGuard`) |
| **Isolamento** | — | Contexto isolado; worktree git opcional |

---

## 4. Escopo da Sprint

### ✅ No Escopo
- [ ] `agents/` (definições, runner, herança de PEP e orçamento).
- [ ] Tipos: explore (read-only), plan, general-purpose, code-review.
- [ ] Tasks (create/update/list/stop), `/agents`, `/tasks`, mensagens entre sessão e agentes.
- [ ] `/loop` e `/review` reescritos sobre subagents.
- [ ] Isolamento por git worktree (opcional).

### 🚫 Fora de Escopo
- Agentes que se auto-criam dinamicamente (v1.5.0).

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/agents/{definitions,runner,tasks}.py [novo]
src/orion/runtime/tools/task.py                [novo]
src/orion/core/engine.py, governance/pep.py    [mod]
tests/unit/test_subagents.py
```

---

## 6. Contratos de Código & Tipagem

```python
class AgentDefinition(BaseModel):
    name: str
    description: str
    tools: list[str] | None      # None = herda, nunca acima do pai
    model_tier: Literal["fast", "balanced", "heavy"]
    max_turns: int = 20
    budget_usd: float | None = None
```

---

## 7. Estratégia de Implementação

1. Runner com contexto isolado e teto de privilégio do pai.
2. Paralelismo e background com eventos de término.
3. Tasks e comandos.
4. Reescrita de `/review` e `/loop`; worktree opcional.

---

## 8. Testes & Critérios de Aceite (DoD)

- Concorrência, cancelamento em cascata, estouro de orçamento, escalada de privilégio negada.
- [ ] mypy/ruff limpos; cobertura ≥ 85%; `.claudex/progress.md` atualizado.

---

## 9. Critérios de Parada

1. Subagent executando algo que o pai não poderia executar.
2. Custo agregado sem teto verificável.
