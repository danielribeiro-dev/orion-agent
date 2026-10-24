# Sprint — [v0.1.0] Sprint 2: Core ReAct Engine, Action-Observation EventBus & Artefatos

> **Status:** 📋 Pronto para Execução  
> **Versão Relacionada:** v0.1.0 (Clean Foundation & Core ReAct Engine)  
> **Responsável / Agente:** Daniel Dev & Antigravity  
> **Data de Início:** A definir  
> **Data de Conclusão:** —  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Desenvolver o núcleo de raciocínio assíncrono (**Core ReAct Engine**), a máquina de estados finitos do agente, o barramento interno de eventos tipados (**EventBus**) baseado no paradigma **Action-Observation**, os delimitadores formais de prompt contra injeção e o **Subsistema de Artefatos Estruturados** (`ArtifactStore`).
* **Dependências Prévias:** Sprint 1 concluída com sucesso.
* **Entregável Verificável:** Um motor cognitivo funcional que recebe mensagens, monta prompts delimitados, despacha eventos `Action` e `Observation` no `EventBus`, controla o teto de passos (*Turn Budgeting*, default: 20 voltas) e gera artefatos markdown estruturados com metadados (`RequestFeedback`, `Summary`).

---

## 2. Contexto de Engenharia

* **Por que esta sprint existe:** Para estabelecer o "cérebro" do O.R.I.O.N com base na melhor arquitetura de ponta (inspirada no Event Stream do OpenHands e no sistema de Artifacts do Antigravity CLI), substituindo qualquer abordagem engessada por um fluxo reativo, auditável e extensível para subagentes.
* **Decisões associadas:** [`CORE_REACT_ENGINE.md`](../../../architecture/CORE_REACT_ENGINE.md) e ADR-008.

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Estado Inicial | Estado Final Esperado (DoD) |
| :--- | :--- | :--- |
| **Loop Cognitivo** | Inexistente | `ReActEngine` assíncrono com suporte a tool calls simuladas e controle de voltas |
| **Event Stream** | Sem pub/sub | `EventBus` pub/sub in-process desacoplado com histórico de `Action` e `Observation` |
| **Segurança de Prompt** | Sem delimitadores | Tags estritas `[INÍCIO DO SISTEMA]`, `[CONTEXTO]`, `[USUÁRIO]` e `[SAÍDA DE FERRAMENTA]` |
| **Artefatos Estruturados**| Inexistente | `ArtifactStore` gravando documentos markdown fora da janela de chat com metadados |

---

## 4. Escopo da Sprint

### ✅ No Escopo (In Scope)
- [ ] Implementação de `src/orion/core/events.py` com modelos imutáveis Pydantic v2:
  - `Action` (identificador, tool, parâmetros, nível de risco, timestamp).
  - `Observation` (action_id, sucesso, resultado, erro, metadados).
  - Eventos de ciclo de vida: `TurnStarted`, `Thinking`, `ActionEmitted`, `ObservationReceived`, `TurnCompleted`.
- [ ] Implementação de `src/orion/core/event_bus.py` (Pub/Sub assíncrono com broadcast de eventos e buffer circular).
- [ ] Implementação de `src/orion/core/state.py` (Máquina de estados finitos: `IDLE` → `CONTEXT_ASSEMBLY` → `REASONING` → `ACTION_PENDING` → `PEP_VALIDATION` → `EXECUTING` → `VERIFYING` → `COMPLETED` / `FAILED`).
- [ ] Implementação de `src/orion/core/errors.py` (Hierarquia tipada de exceções de domínio do ORION).
- [ ] Implementação de `src/orion/core/engine.py` (ReAct Engine assíncrono com controle estrito de `max_turns=20`).
- [ ] Implementação de `src/orion/artifacts/models.py` e `src/orion/artifacts/store.py` (Suporte dual de armazenamento em `~/.orion/brain/<session_id>/artifacts/` global e `.orion/artifacts/` local no projeto ativo).
- [ ] Testes unitários com mocks de LLM simulando turnos completos, emissão de tool calls e criação de artefatos.

### 🚫 Fora de Escopo (Out of Scope / Anti-Metas)
- Não conectar ferramentas reais de sistema operacional (escopo da Sprint 3 via PEP).
- Não persistir histórico em banco de dados SQLite FTS5 (escopo da v0.2.0).

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/
├── core/
│   ├── __init__.py
│   ├── errors.py
│   ├── events.py
│   ├── event_bus.py
│   ├── state.py
│   └── engine.py
└── artifacts/
    ├── __init__.py
    ├── models.py
    └── store.py
tests/unit/
├── test_event_bus.py
├── test_engine.py
└── test_artifacts.py
```

---

## 6. Definition of Done (DoD)

- [ ] `EventBus` despacha e consome eventos `Action` e `Observation` de forma assíncrona e sem vazamentos de memória.
- [ ] `ReActEngine` transita estados corretamente e interrompe loops infinitos ao atingir `max_turns`.
- [ ] Delimitadores formais de prompt são gerados e validados contra injeções.
- [ ] `ArtifactStore` grava arquivos markdown estruturados com metadados (`RequestFeedback`, `Summary`) no caminho correto.
- [ ] Testes unitários de `test_event_bus.py`, `test_engine.py` e `test_artifacts.py` passam com 100% de sucesso.
- [ ] `.claudex/progress.md` atualizado com o encerramento da Sprint 2.
