# O.R.I.O.N — Active Context (Memória de Sessão de Desenvolvimento)

> **Data de Atualização:** 25/10/2026  
> **Status Atual:** v0.1.0 CONCLUÍDA (210 testes passando, Tag v0.1.0 criada) | v0.2.0 Sprint 1 CONCLUÍDA (22 novos testes passando, total 232) | Sprint 2 EM ANDAMENTO (Módulos `vector_store.py` e `hybrid_retriever.py` implementados, testes a criar)  
> **Branch Ativo:** `version/v0.2.0`  
> **Regra Suprema:** Nenhuma linha de código em `src/` é escrita sem o comando explícito de início da Sprint correspondente (Doc-First).

---

## 🎯 Foco Imediato & Estado da v0.2.0 (Cognitive Continuity)
1. **Branch de Trabalho:** `version/v0.2.0`
2. **Sprint 1 (Concluída ✅):**
   - Implementado `src/orion/memory/models.py` (modelos tipados da memória, 5 esferas, timeline e skills).
   - Implementado `src/orion/memory/timeline.py` (TimelineManager com SQLite WAL, FTS5 BM25, DayMarkers e triggers).
   - Testado em `tests/unit/test_timeline.py` (22/22 testes passando com 92% de cobertura no módulo).
3. **Sprint 2 (Em Andamento 🟡):**
   - Dependências adicionadas ao `pyproject.toml` (`aiosqlite`, `fastembed`, `numpy`, `psutil`) e instaladas no ambiente.
   - Implementado `src/orion/memory/vector_store.py` (VectorStore com FastEmbed `bge-small-en-v1.5`, dedup semântico cosseno $\ge 0.92$, dot product NumPy vetorizado).
   - Implementado `src/orion/memory/hybrid_retriever.py` (HybridRetriever com algoritmo Reciprocal Rank Fusion $k=60$ e orçamento estrito $< 1.500$ tokens).
   - **Próximo passo na próxima sessão:** Criar `tests/unit/test_vector_store.py` e `tests/unit/test_hybrid_retriever.py`, validar os 100% de testes e a cobertura $\ge 85\%$ na Sprint 2, avançando para a Sprint 3.
4. **Sprints Restantes da v0.2.0:**
   - Sprint 3: The 5-Sphere Memory, Cognitive Tools & Remote HITL Connector (Telegram).
   - Sprint 4: Universal Skills Standard (`SKILL.md`) & Dynamic Compactor / Branches.

---

## 📌 Próximo Passo
Na próxima sessão, dar continuidade imediata à **Sprint 2 da v0.2.0**:
1. Criar os testes unitários da Sprint 2 (`tests/unit/test_vector_store.py` e `tests/unit/test_hybrid_retriever.py`).
2. Validar CA-02 (FastEmbed ONNX local + deduplicação $\ge 0.92$) e CA-03 (Fusão RRF + teto de 1500 tokens).
3. Concluir Sprint 2 e iniciar Sprint 3 (5 Esferas e Telegram HITL).
