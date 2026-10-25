# Sprint — [v0.2.0] Sprint 2: FastEmbed Local & RRF Hybrid Fusion

> **Status:** 📋 Planejado  
> **Versão Relacionada:** v0.2.0 (Cognitive Continuity: The 5-Sphere Memory, Universal Skills Standard & Dynamic Compaction)  
> **Responsável / Agente:** Daniel Dev & Antigravity  
> **Data de Início:** A definir (Fase 2)  
> **Data de Conclusão:** —  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Implementar a **Camada Semântica Local** da Memória Tríplice utilizando `fastembed` (ONNX Runtime) com o modelo de alta eficiência `bge-small-en-v1.5` (384 dimensões, < 130MB em disco, inferência em CPU local), mecanismo de deduplicação semântica com limiar de cosseno $\ge 0.92$, e o orquestrador de busca híbrida com algoritmo **Reciprocal Rank Fusion (RRF)** com teto rígido de injeção orçamentária ($< 1.500$ tokens).
* **Dependências Prévias:** Sprint 1 concluída (SQLite FTS5 BM25 funcional).
* **Entregável Verificável:** Módulos `src/orion/memory/vector_store.py` e `src/orion/memory/hybrid_retriever.py` totalmente integrados e testados, gerando embeddings offline sem PyTorch pesado e combinando os resultados léxicos e semânticos via RRF.

---

## 2. Contexto de Engenharia

* **Por que esta sprint existe:** Buscas puramente baseadas em palavras-chave (BM25) falham quando o usuário formula uma dúvida usando termos conceituais diferentes daqueles gravados no histórico (ex: "como corrigimos o problema de permissão no socket" vs "EACCES on /var/run/docker.sock"). Por outro lado, bancos vetoriais pesados exigem PyTorch ou serviços externos na nuvem. O ORION precisa de semântica local veloz, leve e offline.
* **Como se encaixa na visão global:** Entrega a Camada 2 (Semântica) e o cérebro de fusão híbrida (RRF) que alimenta o contexto do agente com máxima precisão e economia de tokens.
* **Decisões arquiteturais associadas:** ADR-004 (Memória Tríplice), ADR-012 (FastEmbed `bge-small-en-v1.5` e Fusão Híbrida RRF).

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Estado Inicial (Antes da Sprint) | Estado Final Esperado (DoD) |
| :--- | :--- | :--- |
| **Embeddings** | Inexistentes | `fastembed` local gerando vetores densos (384 dimensões) via ONNX em CPU/GPU |
| **Deduplicação** | Nenhuma | Memórias com similaridade $\ge 0.92$ não duplicam; atualizam peso e timestamp |
| **Recuperação** | Apenas BM25 isolado | Recuperador híbrido fundindo FTS5 + Vetor via algoritmo RRF ($k=60$) |
| **Budget de Contexto** | Ilimitado / manual | Teto determinístico de $< 1.500$ tokens no payload final de injeção |

---

## 4. Escopo da Sprint

### ✅ No Escopo (In Scope)
- [ ] Adicionar dependência `fastembed>=0.3.0` ao `pyproject.toml`.
- [ ] Implementação de `VectorStore` em `src/orion/memory/vector_store.py`:
  - Carregamento lazy do modelo `bge-small-en-v1.5` via ONNX.
  - Armazenamento dos vetores e metadados no SQLite (`vector_embeddings` com serialização binária de floats ou suporte a sqlite-vec caso disponível).
  - Cálculo de similaridade de cosseno em lote (*vectorized dot product* com NumPy).
  - Algoritmo de deduplicação semântica: se `cosine_sim >= 0.92`, executa `touch_memory()` em vez de duplicar.
- [ ] Implementação de `HybridRetriever` em `src/orion/memory/hybrid_retriever.py`:
  - Execução paralela: BM25 (Timeline) e Cosseno (VectorStore).
  - Cálculo da pontuação RRF: $RRF(d) = \sum_{m \in M} \frac{1}{k + r_m(d)}$ com $k=60$.
  - Truncamento orçamentário estrito para garantir que o texto agregado permaneça abaixo de 1.500 tokens.
- [ ] Testes unitários de velocidade de inferência, deduplicação e integridade da fórmula RRF.

### 🚫 Fora de Escopo (Out of Scope / Anti-Metas)
- Não gerenciar fatos estruturados tipados ou perfil de usuário (escopo da Sprint 3).
- Não criar ferramentas de memória no ReAct loop (escopo da Sprint 3).
- Não carregar habilidades `SKILL.md` (escopo da Sprint 4).

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/memory/
├── vector_store.py                    # FastEmbed ONNX local e deduplicação semântica
├── hybrid_retriever.py                # Algoritmo RRF e truncamento orçamentário (<1500 tok)
└── models.py                          # VectorRecord, HybridSearchResult
tests/
└── unit/
    ├── test_vector_store.py           # Testes de embedding e deduplicação
    └── test_hybrid_retriever.py       # Testes de ranking RRF e teto de tokens
```

---

## 6. Contratos de Código & Tipagem

```python
from typing import List, Optional
from pydantic import BaseModel

class VectorRecord(BaseModel):
    id: str
    text: str
    embedding: Optional[List[float]] = None
    similarity_score: float = 0.0
    access_count: int = 1
    updated_at: float

class HybridSearchResult(BaseModel):
    record_id: str
    content: str
    rrf_score: float
    lexical_rank: Optional[int] = None
    semantic_rank: Optional[int] = None
    estimated_tokens: int
```

---

## 7. Estratégia de Implementação (Passo a Passo)

1. **Passo 1:** Configurar `fastembed` e `numpy` no `pyproject.toml`.
2. **Passo 2:** Implementar `VectorStore` encapsulando `TextEmbedding(model_name="BAAI/bge-small-en-v1.5")`.
3. **Passo 3:** Desenvolver tabela relacional para armazenamento de vetores e método de busca vetorial com cálculo de similaridade de cosseno.
4. **Passo 4:** Criar lógica de deduplicação com limiar de 0.92, impedindo crescimento desnecessário do banco.
5. **Passo 5:** Implementar a classe `HybridRetriever` combinando os resultados de `TimelineManager.search_lexical()` e `VectorStore.search_semantic()`.
6. **Passo 6:** Aplicar o ranqueamento RRF com $k=60$ e o filtro de contagem de tokens com estimativa conservadora (4 caracteres $\approx$ 1 token).
7. **Passo 7:** Escrever testes automatizados cobrindo os cenários de similaridade e limites de payload.

---

## 8. Testes Automatizados & Critérios de Aceite (DoD)

### Cenários de Teste Obrigatórios
- **Teste 1:** Geração de embedding para sentença técnica executando em $< 50\text{ ms}$ em CPU.
- **Teste 2:** Inserção de duas frases semanticamente idênticas ("Docker container failed to start" e "Container Docker não conseguiu iniciar") resulta em atualização da memória existente sem criar novo registro duplicado (limiar $\ge 0.92$).
- **Teste 3:** Consulta híbrida via RRF nunca ultrapassa 1.500 tokens no total do payload retornado.

### Definition of Done (DoD)
- [ ] `VectorStore` e `HybridRetriever` implementados sem dependência de PyTorch.
- [ ] Modelo `bge-small-en-v1.5` operando 100% offline via ONNX Runtime.
- [ ] `pytest tests/unit/test_vector_store.py tests/unit/test_hybrid_retriever.py` passando com 100% de sucesso.
- [ ] Cobertura de testes dos módulos $\ge 90\%$.
- [ ] Documentação de progresso atualizada em `.claudex/progress.md`.
