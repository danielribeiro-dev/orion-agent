# Sprint — v0.5.0 Sprint 2: Loop Agêntico Nativo

> **Status:** 📋 Planejando  
> **Versão Relacionada:** v0.5.0  
> **Responsável / Agente:** Daniel Dev & Claude  
> **Data de Início:** —  
> **Data de Conclusão:** —  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Substituir o protocolo `<tool_call>` em texto por `tool_use`/`tool_result` estruturados, com schemas JSON, validação e tools paralelas.
* **Dependências Prévias:** Sprint 1.
* **Entregável Verificável:** conversa real com várias tools por resposta, interrupção segura e PEP em cada chamada.

---

## 2. Contexto de Engenharia

* **Por que existe:** hoje 1 tool por resposta, regex, JSON inválido vira resposta final, prompt monolítico que impede cache de prefixo (`core/engine.py:304-361`, `tui/session.py:63-155`).
* **Encaixe:** ADR-021.

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Antes | Depois |
| :--- | :--- | :--- |
| **Tools** | Assinaturas em texto | `name`, `description`, `input_schema` validado |
| **Conversa** | Prompt único reconstruído | Alternância assistant/user com `tool_result` |
| **Execução** | Sequencial, 1 por turno | Read-only em paralelo, mutantes em série |
| **Risco** | `_RISK_MAP` duplicado | Fonte única em `governance/permissions.py` |

---

## 4. Escopo da Sprint

### ✅ No Escopo
- [ ] `BaseTool.input_schema` + validação antes de executar; erro de validação volta como `tool_result` com `is_error`.
- [ ] Engine reescrito (FSM mantida): `stop_reason` (`end_turn`, `tool_use`, `max_tokens` com continuação, `refusal`).
- [ ] Execução paralela de tools somente leitura.
- [ ] Cancelamento (Esc/Ctrl+C) com `tool_result` sintético "cancelado".
- [ ] Remoção de `TOOL_PROTOCOL`/`ToolCallFilter`; renderer consome eventos tipados.
- [ ] Manter limite de turnos, anti-injection, auditoria, `ChangeTracker`/`/undo`.

### 🚫 Fora de Escopo
- Novas tools (Sprint 4), subagents (Sprint 6).

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/core/{engine,events}.py
src/orion/runtime/{local_provider.py,tools/base.py,tools/*.py}
src/orion/governance/permissions.py
src/orion/tui/{session,stream_renderer}.py
tests/unit/test_engine_toolcalls.py; tests/e2e/test_security_audit.py (regressão)
```

---

## 6. Contratos de Código & Tipagem

```python
class BaseTool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    input_schema: ClassVar[dict[str, Any]]
    read_only: ClassVar[bool] = False
    async def run(self, **params: Any) -> RuntimeResult: ...
```

---

## 7. Estratégia de Implementação

1. Schemas e validação nas 5 tools + tools de memória + adaptador MCP.
2. Unificar níveis de risco em uma única fonte.
3. Reescrever o engine contra roteiros determinísticos.
4. Paralelismo e cancelamento.
5. Migrar a `AgentSession` e remover o protocolo em texto.

---

## 8. Testes & Critérios de Aceite (DoD)

- Roteiros: múltiplas tools, tool inválida, params inválidos, cancelamento, `max_tokens`.
- Toda a suíte de segurança e2e passa; nenhuma tool executa fora do PEP.
- [ ] mypy/ruff limpos; cobertura ≥ 85%; `.claudex/progress.md` atualizado.

---

## 9. Critérios de Parada

1. Qualquer caminho que execute tool sem passar pelo PEP.
2. Necessidade de quebrar o contrato `RuntimeResult`/`Observation`.
