# Sprint — [v0.2.0] Sprint 1: Main Timeline & SQLite FTS5

> **Status:** 📋 Planejado  
> **Versão Relacionada:** v0.2.0 (Cognitive Continuity: Triple Memory, Agent Skills Standard & Dynamic Compaction)  
> **Responsável / Agente:** Daniel Dev & Antigravity  
> **Data de Início:** A definir (Fase 2)  
> **Data de Conclusão:** —  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Implementar o motor da **Main Timeline** permanente e o armazenamento de eventos em SQLite em modo WAL com indexação FTS5 (`~/.orion/timeline.db`), garantindo gravação cronológica append-only com marcadores de virada de dia (*Day Markers*) e busca textual exata (BM25) com latência sub-10ms para erros, código, hashes e comandos.
* **Dependências Prévias:** v0.1.0 (Core ReAct Engine, Action-Observation Event Stream e sistema de arquivos configurado).
* **Entregável Verificável:** Módulo `src/orion/memory/timeline.py` totalmente testado, capaz de persistir o fluxo de eventos da sessão, inserir marcadores diários e executar buscas BM25 com paginação e ranking por relevância temporal.

---

## 2. Contexto de Engenharia

* **Por que esta sprint existe:** Agentes convencionais esquecem tudo entre reinicializações ou dependem de buscas rudimentares em arquivos de log sem índice. O ORION precisa de uma espinha dorsal cronológica indelével onde cada ação e observação fica indexada no próprio SO do usuário.
* **Como se encaixa na visão global:** Constitui a primeira camada da Memória Tríplice (Camada Léxica & Episódica), base fundamental para que o agente tenha continuidade perpétua e saiba exatamente o que foi executado nos dias anteriores.
* **Decisões arquiteturais associadas:** ADR-004 (Memória Tríplice), ADR-008 (Action-Observation Event Stream Imutável).

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Estado Inicial (Antes da Sprint) | Estado Final Esperado (DoD) |
| :--- | :--- | :--- |
| **Banco de Dados** | Inexistente | `~/.orion/timeline.db` criado automaticamente em modo WAL |
| **Estrutura de Tabelas** | Inexistente | Tabelas `events`, `day_markers` e tabela virtual FTS5 `timeline_fts` configuradas |
| **Busca Léxica** | Não existe | Busca BM25 via FTS5 respondendo em $< 10\text{ ms}$ com rankeamento de relevância |
| **Testes** | 0 testes de timeline | Testes unitários com banco em memória (`:memory:`) e testes de carga simulando 10k eventos |

---

## 4. Escopo da Sprint

### ✅ No Escopo (In Scope)
- [ ] Implementação de `TimelineManager` em `src/orion/memory/timeline.py` com conexão assíncrona SQLite WAL (`aiosqlite`).
- [ ] Criação do schema SQL com migrações idênticas a:
  - Tabela `timeline_events` (id, session_id, timestamp, event_type, source, content, metadata_json).
  - Tabela virtual FTS5 `timeline_fts` vinculada via triggers para inserção/atualização automática de termos.
  - Tabela `day_markers` para registrar viradas de data (`YYYY-MM-DD`).
- [ ] Métodos de alta performance:
  - `append_event(event: TurnEvent) -> int`: Persistência atômica.
  - `ensure_day_marker(date: datetime.date) -> None`: Inserção automática de marcador no primeiro evento do dia.
  - `search_lexical(query: str, limit: int = 20) -> list[TimelineRecord]`: Consulta BM25 com snippet e score.
  - `get_recent_history(limit: int = 50) -> list[TimelineRecord]`: Retorno cronológico rápido.
- [ ] Testes unitários e benchmarks de busca cobrindo inserção em massa e recuperação por termos de código (ex: stack traces, nomes de arquivos, parâmetros).

### 🚫 Fora de Escopo (Out of Scope / Anti-Metas)
- Não gerar embeddings vetoriais ou carregar modelos ONNX (escopo da Sprint 2).
- Não gerenciar fatos confirmados ou preferências estruturadas (escopo da Sprint 3).
- Não implementar branches contextuais ou compactador (escopo da Sprint 4).

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/memory/
├── __init__.py
├── models.py                          # TimelineRecord, DayMarkerRecord
└── timeline.py                        # TimelineManager assíncrono com WAL e FTS5
tests/
└── unit/
    └── test_timeline.py               # Suíte completa de testes da timeline
```

---

## 6. Contratos de Código & Tipagem

```python
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field

class TimelineRecord(BaseModel):
    id: int
    session_id: str
    timestamp: datetime
    event_type: str
    source: str
    content: str
    bm25_rank: Optional[float] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class DayMarkerRecord(BaseModel):
    date_str: str
    created_at: datetime
    summary: Optional[str] = None
```

---

## 7. Estratégia de Implementação (Passo a Passo)

1. **Passo 1:** Configurar dependência `aiosqlite` no `pyproject.toml`.
2. **Passo 2:** Definir modelos Pydantic `TimelineRecord` e `DayMarkerRecord` em `src/orion/memory/models.py`.
3. **Passo 3:** Implementar `TimelineManager` com inicialização de schemas (`PRAGMA journal_mode=WAL;`, `CREATE VIRTUAL TABLE timeline_fts USING fts5(...)`).
4. **Passo 4:** Implementar rotinas de inserção de `DayMarker` e inserção transacional de eventos.
5. **Passo 5:** Implementar consultas FTS5 com operador `MATCH` e cálculo de ranking BM25 nativo do SQLite.
6. **Passo 6:** Escrever suíte de testes unitários em `tests/unit/test_timeline.py` validando integridade, concorrência e velocidade de busca.

---

## 8. Testes Automatizados & Critérios de Aceite (DoD)

### Cenários de Teste Obrigatórios
- **Teste 1:** Persistência de 1.000 eventos e recuperação de erro específico (`RuntimeError: Connection reset`) via FTS5 em $< 10\text{ ms}$.
- **Teste 2:** Virada de dia cria `DayMarker` único para a data sem duplicatas.
- **Teste 3:** Modos concorrentes de leitura e escrita não causam lock de banco de dados (validação WAL).

### Definition of Done (DoD)
- [ ] `TimelineManager` implementado com tipagem estrita Pydantic v2.
- [ ] Busca FTS5 respondendo com pontuação BM25 e snippets destacados.
- [ ] Suíte `pytest tests/unit/test_timeline.py` passando com 100% de sucesso.
- [ ] Cobertura de testes do módulo $\ge 90\%$.
- [ ] Documentação de progresso atualizada em `.claudex/progress.md`.
