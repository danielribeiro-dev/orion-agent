# Spec — [v0.2.0] Continuous Timeline & Triple Memory

> **Status:** 📋 Planejado  
> **Criada em:** 2026-10-24  
> **Concluída em:** —  
> **Autor(es):** Daniel Dev & Antigravity  
> **Branch:** `version/v0.2.0`  

---

## 1. Visão Geral & Motivação

### 1.1 Objetivo
Implementar a arquitetura da **Linha do Tempo Contínua** e a **Memória Tríplice** do ORION, eliminando para sempre o conceito de conversas descartáveis e permitindo que o assistente mantenha a continuidade de contexto ao longo dos dias, com recuperação precisa e sem estourar a janela de contexto.

### 1.2 Por que agora?
Após a consolidação do Core ReAct Loop na v0.1.0, o ORION precisa de memória de longo prazo persistente para que suas decisões e aprendizados sobrevivam entre sessões e reinicializações do sistema.

### 1.3 O que NÃO é escopo (anti-metas)
- Não plugar modelos de visão ou áudio.
- Não construir a interface TUI avançada (escopo da v0.4.0).

---

## 2. Decisões Arquiteturais & Diretrizes de Design

- **ADR-004:** Memória Tríplice (FTS5 + FastEmbed + Fatos estruturados).
- Especificação técnica: [`TRIPLE_MEMORY.md`](../../../architecture/TRIPLE_MEMORY.md) e [`TIMELINE_SYSTEM.md`](../../../architecture/TIMELINE_SYSTEM.md).

---

## 3. Divisão em Sprints & Entregáveis

| Sprint | Nome da Sprint | Objetivo Principal | Documento | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Sprint 1** | Main Timeline & SQLite FTS5 | Linha do tempo em SQLite WAL com busca BM25 exata | [`sprints/sprint-1.md`](sprints/sprint-1.md) | 📋 Planejado |
| **Sprint 2** | FastEmbed Local (ONNX Vector) | Embeddings semânticos locais sem PyTorch pesado | [`sprints/sprint-2.md`](sprints/sprint-2.md) | 📋 Planejado |
| **Sprint 3** | Memória Estruturada & Perfil | Fatos confirmados, preferências e estado em JSON/SQLite | [`sprints/sprint-3.md`](sprints/sprint-3.md) | 📋 Planejado |
| **Sprint 4** | Branches & Síntese de Checkpoints | Motor de ramificações e síntese na Main Timeline | [`sprints/sprint-4.md`](sprints/sprint-4.md) | 📋 Planejado |
