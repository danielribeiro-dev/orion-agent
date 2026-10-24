# Sprint — [v0.1.0] Sprint 2: Core ReAct Engine & EventBus

> **Status:** 📋 Planejado  
> **Versão Relacionada:** v0.1.0 (Clean Foundation & Core ReAct Engine)  
> **Responsável / Agente:** Daniel Dev & Antigravity  
> **Data de Início:** A definir  
> **Data de Conclusão:** —  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Desenvolver o núcleo de raciocínio assíncrono (**Core ReAct Loop**), a máquina de estados finitos do agente, o barramento interno de eventos tipados (`EventBus`) e a delimitação formal de prompts com blindagem contra injeção de instruções.
* **Dependências Prévias:** Sprint 1 concluída com sucesso.
* **Entregável Verificável:** Um motor de ReAct funcional que recebe uma mensagem, injeta o contexto delimitado, processa a intenção com suporte a chamadas de ferramentas (*tool calling*) simuladas e emite eventos de progresso no `EventBus`.

---

## 2. Contexto de Engenharia

* **Por que esta sprint existe:** Substituir o antigo roteador de intents rígido (que quebrava quando o usuário fazia solicitações compostas) por um loop dinâmico de percepção e raciocínio real (ReAct), onde o agente é capaz de decompor problemas e encadear passos com controle estrito de voltas (*Turn Budgeting*).
* **Decisões associadas:** Especificação [`CORE_REACT_ENGINE.md`](../../../architecture/CORE_REACT_ENGINE.md).

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Estado Inicial | Estado Final Esperado (DoD) |
| :--- | :--- | :--- |
| **Loop Cognitivo** | Inexistente no novo repo | `ReActEngine` assíncrono com suporte a streaming e tool calling |
| **Eventos Internos** | Sem pub/sub | `EventBus` pub/sub in-process com histórico circular de eventos |
| **Segurança de Prompt** | Sem delimitadores | Tags `[INÍCIO DO SISTEMA]`, `[CONTEXTO]` e `[USUÁRIO]` ativas |

---

## 4. Escopo da Sprint

### ✅ No Escopo (In Scope)
- [ ] Implementação de `src/orion/core/event_bus.py` (Pub/Sub assíncrono com eventos `TurnStarted`, `Thinking`, `ToolCallEmitted`, `ToolResultReceived`, `TurnCompleted`).
- [ ] Implementação de `src/orion/core/errors.py` (Hierarquia de exceções de domínio do ORION).
- [ ] Implementação de `src/orion/core/engine.py` (State Machine do ReAct: IDLE → CONTEXT_ASSEMBLY → INFERENCE → TOOL_EXECUTION → VERIFICATION → IDLE).
- [ ] Controle de orçamento de turnos (limite máximo de 20 passos por tarefa para evitar loops infinitos).
- [ ] Testes unitários com mocks de LLM simulando emissão de tool calls e respostas conversacionais diretas.

### 🚫 Fora de Escopo (Out of Scope / Anti-Metas)
- Não conectar ferramentas reais de sistema operacional (escopo da Sprint 3 via PEP).
- Não persistir histórico em banco de dados SQLite (escopo da v0.2.0).

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/core/
  ├── __init__.py
  ├── errors.py
  ├── event_bus.py
  ├── state.py
  └── engine.py
tests/unit/core/
  ├── test_event_bus.py
  └── test_engine.py
```

---

## 6. Definition of Done (DoD)

- [ ] `EventBus` opera assincronamente sem vazamento de memória ou eventos pendentes.
- [ ] `ReActEngine` processa turnos e transita estados corretamente.
- [ ] O limite de turnos interrompe loops descontrolados com explicação legível.
- [ ] Testes unitários de `test_event_bus.py` e `test_engine.py` passam com 100% de sucesso.
- [ ] `.claudex/progress.md` atualizado.
