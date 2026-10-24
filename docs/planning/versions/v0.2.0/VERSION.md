# Spec — [v0.2.0] Cognitive Continuity: Triple Memory, Agent Skills Standard & Dynamic Compaction

> **Status:** 📋 Especificação Completa e Congelada para Execução após a v0.1.0  
> **Criada em:** 2026-10-24  
> **Concluída em:** —  
> **Autor(es):** Daniel Dev & Antigravity (Pair Programming)  
> **Branch:** `version/v0.2.0`  

---

## 1. Visão Geral & Motivação

### 1.1 Objetivo
Implementar o subsistema de **Continuidade Cognitiva e Inteligência Persistente** do **O.R.I.O.N (Operational Reasoning & Intelligence Orchestration Network)**, dotando o sistema de:
1. **Memória Tríplice Coordenada:** 
   - Camada Léxica Episódica: SQLite WAL com busca FTS5 / BM25 sub-10ms em `~/.orion/timeline.db`.
   - Camada Semântica Local: `fastembed` executando modelo ONNX `bge-small-en-v1.5` localmente (zero PyTorch, < 130MB, deduplicação com cosseno $\ge 0.92$).
   - Camada Estruturada de Fatos: Entidades tipadas com ciclo de certeza anti-envenenamento (`CONFIRMED`, `INFERRED`, `DEPRECATED`).
   - Recuperação Híbrida RRF (*Reciprocal Rank Fusion*) com teto rígido de injeção de contexto ($< 1.500$ tokens).
2. **Padrão Universal `Agent Skills` (`SKILL.md`):**
   - Adoção integral do padrão aberto interoperável de mercado (adotado por Claude Code, Antigravity, OpenHands e Microsoft).
   - Divulgação Progressiva (*Progressive Disclosure*): consumo mínimo de tokens no boot (~60 tokens por skill) e carregamento integral sob demanda.
   - Suporte hierárquico: Workspace (`<workspace>/.orion/skills/`), Global (`~/.orion/skills/`) e Builtin (`src/orion/builtin/skills/`).
3. **Dynamic Context Compactor & Branches:**
   - Auto-compaction silenciosa com notificação no terminal ao atingir 80% da janela de contexto.
   - Comando `/compact` com suporte a foco direcional.
   - Preservação intacta de *vital tail* (últimos 3 a 5 turnos), arquivos ativos modificados e objetivos.
   - Ramificações contextuais (`/branch <slug>`, `/merge`) com síntese de checkpoints imutáveis na Main Timeline.
4. **Ferramentas Cognitivas Nativas no ReAct Loop:**
   - `memorize`, `recall` e `deprecate_fact`.

### 1.2 Por que agora?
Após a consolidação da fundação limpa, do ReAct Engine e das 5 ferramentas primitivas na v0.1.0, o ORION precisa de memória de longo prazo e modularidade de habilidades para evoluir de um assistente de terminal para um **piloto administrativo e técnico pessoal contínuo**. Sem compactação e sem o padrão universal de skills, qualquer sessão de trabalho longa sucumbe à degradação de contexto e à perda de aprendizados.

### 1.3 O que NÃO é escopo (anti-metas)
- Não plugar hardware ou pipelines de áudio/voz (escopo da v0.5.0).
- Não criar interface TUI interativa complexa em Rich com diffs gráficos (escopo da v0.4.0).
- Não criar cliente de conexão com servidores MCP externos (escopo da v0.4.0).
- Não implementar sandbox Bubblewrap em contêineres host (escopo da v1.5.0).

---

## 2. Decisões Arquiteturais & Diretrizes de Design (ADRs)

- **ADR-004:** Memória Tríplice (FTS5 + FastEmbed + Fatos estruturados).
- **ADR-010:** Padrão Universal `Agent Skills` (`SKILL.md`) com Progressive Disclosure em 3 fases (Discovery, Activation, Execution).
- **ADR-011:** Dynamic Context Compactor: disparo automático a 80% do budget de contexto com preservação de *vital tail* e arquivos ativos.
- **ADR-012:** Modelo de Embedding Local `bge-small-en-v1.5` (384 dimensões, ONNX Runtime em CPU/GPU) e Fusão Híbrida RRF com teto estrito de 1.500 tokens.
- **ADR-013:** Prevenção de *Memory Poisoning* via ciclo de vida de certezas tipadas (`CONFIRMED`, `INFERRED`, `DEPRECATED`) e ferramentas cognitivas nativas (`memorize`, `recall`, `deprecate_fact`).

---

## 3. Divisão em Sprints & Entregáveis

| Sprint | Nome da Sprint | Objetivo Principal | Documento | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Sprint 1** | Main Timeline & SQLite FTS5 | Linha do tempo perpétua em SQLite WAL com busca BM25 sub-10ms e Day Markers | [`sprints/sprint-1.md`](sprints/sprint-1.md) | 📋 Planejado |
| **Sprint 2** | FastEmbed Local & RRF Fusion | Embeddings locais ONNX (`bge-small-en-v1.5`), deduplicação ($\ge 0.92$) e fusão RRF | [`sprints/sprint-2.md`](sprints/sprint-2.md) | 📋 Planejado |
| **Sprint 3** | Fatos Estruturados & Cognitive Tools | Entidades tipadas com ciclo anti-envenenamento, índice `MEMORY.md` e tools (`memorize`, `recall`, `deprecate_fact`) | [`sprints/sprint-3.md`](sprints/sprint-3.md) | 📋 Planejado |
| **Sprint 4** | Universal Skills Standard & Compactor | Padrão `SKILL.md` com Progressive Disclosure, comando `/compact`, branches e checkpoints | [`sprints/sprint-4.md`](sprints/sprint-4.md) | 📋 Planejado |

---

## 4. Arquitetura Alvo & Componentes Afetados

```
src/orion/
├── memory/
│   ├── __init__.py
│   ├── models.py                      # Modelos FactEntry, FactStatus, MemoryRecord
│   ├── timeline.py                    # SQLite WAL FTS5 Timeline & DayMarkers
│   ├── vector_store.py                # FastEmbed ONNX local (bge-small-en-v1.5) & Cosine
│   ├── facts_store.py                 # Fatos estruturados tipados com ciclo CONFIRMED/INFERRED
│   ├── hybrid_retriever.py            # Reciprocal Rank Fusion (RRF) com budget de 1500 tokens
│   └── tools.py                       # Ferramentas cognitivas: memorize, recall, deprecate_fact
├── skills/
│   ├── __init__.py
│   ├── models.py                      # SkillMetadata (Pydantic v2), SkillBundle
│   ├── loader.py                      # Hierarquia: Workspace > Global > Builtin
│   └── engine.py                      # Progressive Disclosure & Injeção de Contexto
├── timeline/
│   ├── __init__.py
│   ├── branch_manager.py              # Ramificações contextuais (/branch, /merge)
│   ├── compactor.py                   # Dynamic Context Compactor (80% threshold + /compact)
│   └── checkpoint_synthesis.py        # Síntese de 3 a 5 linhas back-propagada para Main Timeline
└── builtin/
    └── skills/
        └── system-doctor/
            └── SKILL.md               # Skill nativa inicial de diagnóstico
```

---

## 5. Matriz de Critérios de Aceite da Versão (DoD Global)

| ID | Cenário | Comportamento Esperado | Como Validar | Status |
|:---|:---|:---|:---|:---|
| CA-01 | Main Timeline & FTS5 | Eventos gravados em WAL com busca BM25 retornando em $< 10\text{ ms}$ | `pytest tests/unit/test_timeline.py` | ⏳ Pendente |
| CA-02 | FastEmbed Local & RRF | Embeddings ONNX gerados em CPU local sem PyTorch; deduplicação em $\ge 0.92$ | `pytest tests/unit/test_vector_store.py` | ⏳ Pendente |
| CA-03 | Blindagem Anti-Poisoning | Fatos inferidos nunca sobrescrevem regras confirmadas pelo usuário | `pytest tests/unit/test_facts_store.py` | ⏳ Pendente |
| CA-04 | Ferramentas Cognitivas | `memorize`, `recall` e `deprecate_fact` funcionais no ReAct Engine | `pytest tests/unit/test_memory_tools.py` | ⏳ Pendente |
| CA-05 | Progressive Skills Standard | Boot varre skills consumindo $< 100$ tokens/skill; `use_skill` carrega instruções completas | `pytest tests/unit/test_skills_loader.py` | ⏳ Pendente |
| CA-06 | Dynamic Compactor | Compacting automático a 80% do budget preserva *vital tail* e caminhos de arquivos ativos | `pytest tests/unit/test_compactor.py` | ⏳ Pendente |
| CA-07 | Branches & Síntese | Merge de branch gera checkpoint conciso na Main Timeline e arquiva logs brutos | `pytest tests/unit/test_branches.py` | ⏳ Pendente |
| CA-08 | Cobertura de Testes | Suíte completa da v0.2.0 passando com cobertura global $\ge 85\%$ | `pytest --cov=src/orion` | ⏳ Pendente |

---

## 6. Checklist de Conclusão da Spec (Congelamento)

- [x] Especificação técnica e arquitetural da v0.2.0 alinhada e aprovada pelo usuário.
- [x] As 4 sprints da v0.2.0 devidamente criadas e detalhadas em `docs/planning/versions/v0.2.0/sprints/`.
- [ ] Implementação de todas as 4 sprints concluída com testes automatizados.
- [ ] Bateria de testes com cobertura $\ge 85\%$.
- [ ] Tag Git `v0.2.0` criada.
