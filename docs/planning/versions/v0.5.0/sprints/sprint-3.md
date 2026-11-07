# Sprint — v0.5.0 Sprint 3: Contexto, Sessões & Memória

> **Status:** 📋 Planejando  
> **Versão Relacionada:** v0.5.0  
> **Responsável / Agente:** Daniel Dev & Claude  
> **Data de Início:** —  
> **Data de Conclusão:** —  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Sessões longas e baratas: prompt em camadas cacheáveis, auto-compactação, poda de resultados, persistência/resume/rewind e memória realmente ligada ao turno.
* **Dependências Prévias:** Sprint 2.
* **Entregável Verificável:** sessão longa sem estourar contexto, retomável e com recall vetorial funcionando.

---

## 2. Contexto de Engenharia

* **Por que existe:** compactação só manual e por regras; observações intra-turno sem poda; `HybridRetriever`, skills, manifest e `EnvironmentMonitor` existem mas não estão ligados à `AgentSession`; `history` só em RAM.
* **Encaixe:** habilita cache (custo) e continuidade (Jarvis).

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Antes | Depois |
| :--- | :--- | :--- |
| **Compactação** | `/compact` manual | Automática ~80% antes de cada chamada, resumo por LLM barato |
| **Sessão** | RAM | JSONL em `~/.orion/sessions/`, `--continue`, `--resume`, `/rewind` |
| **Memória** | Só `FactsStore` | Recall híbrido, skills, manifest, MEMORY.md |
| **Decisões** | Só ADRs manuais | Tool `record_decision` + recall |

---

## 4. Escopo da Sprint

### ✅ No Escopo
- [ ] Prompt em camadas: system → tools → manifest/skills → `CLAUDE.md`/`ORION.md` → histórico, com breakpoints de cache.
- [ ] Auto-compactação, poda de `tool_result` antigos, limites de saída por tool, `count_tokens`.
- [ ] Ligar `HybridRetriever`, `skills_engine`, `ManifestGenerator`, `EnvironmentMonitor`, `FileSyncer`.
- [ ] Sessões persistentes + `/resume`, `/rewind` (conversa e arquivos).
- [ ] Decision log (`record_decision`) com fato CONFIRMED e arquivo em `.orion/decisions/`.
- [ ] **Tool calling nativo nos providers legados (herdado da Sprint 2):** `OpenRouter` e `Ollama` passam a enviar `tools`/`tool_choice` (formato OpenAI), a montar `tool_use` a partir de `delta.tool_calls` e a converter `tool_use`/`tool_result` do histórico; o failover Anthropic -> OpenRouter -> Ollama preserva tools e histórico estruturado em vez de achatar para texto. Modelos locais sem suporte a tools degradam para texto com aviso explícito.
- [ ] Remover `mcp_schema` (redundante desde a Sprint 2: tools MCP já levam o schema completo).

### 🚫 Fora de Escopo
- Daemon e sessão compartilhada entre clientes (Sprint 7).

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/timeline/compactor.py          [mod]
src/orion/gateway/providers/{openrouter,local_ollama}.py [mod]  tool calling nativo
src/orion/gateway/failover.py            [mod]  preservar tools no failover
src/orion/sessions/{store,transcript}.py [novo]
src/orion/memory/{tools,hybrid_retriever}.py [mod]
src/orion/tui/{session.py,commands/*}    [mod]
tests/unit/test_autocompact.py, test_sessions.py, test_decisions.py, test_legacy_tool_calling.py
```

---

## 6. Contratos de Código & Tipagem

```python
class SessionStore(Protocol):
    def append(self, session_id: str, entry: TranscriptEntry) -> None: ...
    def load(self, session_id: str) -> list[TranscriptEntry]: ...
    def list(self, workspace: Path) -> list[SessionMeta]: ...
    def rewind(self, session_id: str, to_entry: int) -> None: ...
```

---

## 7. Estratégia de Implementação

1. Montagem de prompt em camadas e medição de cache hit.
2. Compactação automática e poda.
3. Fiação de memória/skills/manifest.
4. Store de sessões, resume e rewind.
5. Decision log e integração com `/plan` e `/grill-me`.

---

## 8. Testes & Critérios de Aceite (DoD)

- Compactação sob carga preserva tarefa ativa e arquivos relevantes.
- Resume reproduz fielmente; rewind restaura conversa e arquivos.
- Recall vetorial entra no turno dentro do orçamento de 1500 tokens.
- Roteiro com `tool_use` paralelo funciona via OpenRouter e Ollama falsos (servidor HTTP simulado) e atravessa um failover sem perder `tool_result`.
- [ ] mypy/ruff limpos; cobertura ≥ 85%; `.claudex/progress.md` atualizado.

---

## 9. Critérios de Parada

1. Perda de dados de sessão em teste de resume/rewind.
2. Compactação que descarte instrução ativa do usuário.
