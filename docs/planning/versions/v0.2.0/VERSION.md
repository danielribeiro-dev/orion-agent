# Spec — [v0.2.0] Cognitive Continuity: The 5-Sphere Memory, Universal Skills Standard & Dynamic Compaction

> **Status:** 📋 Especificação Formalizada e Atualizada para Execução  
> **Criada em:** 2026-10-24  
> **Atualizada em:** 2026-10-25  
> **Autor(es):** Daniel Dev & Antigravity (Pair Programming)  
> **Branch:** `version/v0.2.0`  

---

## 1. Visão Geral & Motivação

### 1.1 Objetivo
Implementar o subsistema de **Continuidade Cognitiva, Inteligência Persistente e Consciência Operacional** do **O.R.I.O.N (Operational Reasoning & Intelligence Orchestration Network)**, dotando o sistema de:

1. **A Arquitetura das 5 Esferas Cognitivas (*The 5-Sphere Cognitive Architecture*):**
   - **`user_profile`:** Identidade do desenvolvedor, pronome/tratamento formal preferido (`"Senhor"`, `"Daniel"`), matriz de maestria em ferramentas (`tool_mastery`: `expert`, `beginner`) e canais de contato remoto out-of-band.
   - **`system_identity`:** Identidade dual com **Origem Imutável** (concebido por Daniel, github: [`danielribeiro-dev`](https://github.com/danielribeiro-dev)) e **Persona Ativa Modular** (estilo Jarvis: mordomo refinado, cirúrgico em execuções de terminal, rico e didático em explicações de conceitos).
   - **`system_environment`:** Monitoramento passivo do host via `psutil` (RAM livre, CPU load, modo de display Wayland/X11 vs Headless) com o **Headroom Guard** (bloqueio determinístico de navegadores e mídias pesadas se RAM livre $< 1.5\text{ GB}$).
   - **`project_decisions`:** Base estruturada de regras e ADRs do repositório com máquina de estados de certeza anti-envenenamento (`CONFIRMED`, `INFERRED`, `DEPRECATED`) e sincronização bidirecional em `.orion/memory/MEMORY.md`.
   - **`timeline_episodic`:** Linha do tempo perpétua em SQLite WAL com FTS5 BM25 sub-10ms e Day Markers (`DayMarker: YYYY-MM-DD`).

2. **Mecanismo Anti-Afogamento (*Progressive Cognitive Unpacking - PCU*):**
   - Injeção inicial de um **Cognitive Manifest** ultra-compacto ($< 250$ tokens) no System Prompt contendo metadados de alto nível e ponteiros.
   - Desempacotamento cirúrgico sob demanda acionado por ferramentas primitivas (`recall`, `inspect_environment`) apenas quando o turno exigir.
   - Recuperação Híbrida RRF (*Reciprocal Rank Fusion*, $k=60$) com teto orçamentário estrito ($< 1.500$ tokens) fundindo BM25 e FastEmbed ONNX local (`bge-small-en-v1.5`, 384 dimensões).

3. **Escalonamento Remoto Out-of-Band (HITL via Telegram Bot):**
   - Quando o ORION executa tarefas em segundo plano ou em modo ambiente/daemon e necessita de autorização PEP (Level 2 ou 3) com inatividade no terminal local ($> 180$s), despacha um ping seguro no Telegram do desenvolvedor com botões inline de aprovação.
   - Ao receber o toque no celular, a tarefa retoma a execução no PC sem travar.

4. **Padrão Universal `Agent Skills` (`SKILL.md`):**
   - Adoção integral do padrão aberto interoperável de mercado (adotado por Claude Code, Antigravity e OpenHands).
   - Divulgação Progressiva (*Progressive Disclosure*): consumo mínimo de tokens no boot (~60 tokens por skill) e carregamento integral sob demanda.
   - Suporte hierárquico: Workspace (`<workspace>/.orion/skills/`), Global (`~/.orion/skills/`) e Builtin (`src/orion/builtin/skills/`).

5. **Dynamic Context Compactor & Branches:**
   - Auto-compaction silenciosa com notificação no terminal ao atingir 80% da janela de contexto.
   - Comando `/compact` com suporte a foco direcional.
   - Preservação intacta de *vital tail* (últimos 3 a 5 turnos), arquivos ativos modificados e objetivos.
   - Ramificações contextuais (`/branch <slug>`, `/merge`) com síntese de checkpoints imutáveis na Main Timeline.

### 1.2 Por que agora?
Após a consolidação da fundação limpa, do ReAct Engine e das 5 ferramentas primitivas na v0.1.0, o ORION precisa de memória de longo prazo, consciência do ambiente físico e modularidade de habilidades para evoluir de um assistente de terminal para um **piloto administrativo e técnico pessoal contínuo**.

### 1.3 O que NÃO é escopo (anti-metas)
- Não plugar hardware ou pipelines de áudio/voz de microfone (escopo da v0.5.0).
- Não criar interface TUI interativa complexa em Rich com diffs gráficos ao vivo (escopo da v0.4.0).
- Não criar cliente de conexão com servidores MCP externos (escopo da v0.4.0).
- Não implementar sandbox Bubblewrap em contêineres host (escopo da v1.5.0).

---

## 2. Decisões Arquiteturais & Diretrizes de Design (ADRs)

- **ADR-004:** Memória Tríplice Coordenada (FTS5 + FastEmbed + Fatos estruturados).
- **ADR-010:** Padrão Universal `Agent Skills` (`SKILL.md`) com Progressive Disclosure em 3 fases (Discovery, Activation, Execution).
- **ADR-011:** Dynamic Context Compactor: disparo automático a 80% do budget de contexto com preservação de *vital tail* e arquivos ativos.
- **ADR-012:** Modelo de Embedding Local `bge-small-en-v1.5` (384 dimensões, ONNX Runtime em CPU/GPU) e Fusão Híbrida RRF com teto estrito de 1.500 tokens.
- **ADR-013:** Prevenção de *Memory Poisoning* via ciclo de vida de certezas tipadas (`CONFIRMED`, `INFERRED`, `DEPRECATED`) e ferramentas cognitivas nativas (`memorize`, `recall`, `deprecate_fact`).
- **ADR-014:** Arquitetura das 5 Esferas Cognitivas e Progressive Cognitive Unpacking (PCU) com injeção do Cognitive Manifest $< 250$ tokens.
- **ADR-015:** Environment Telemetry Monitor passivo e Headroom Guard (bloqueio determinístico de browser se RAM livre $< 1.5\text{ GB}$).
- **ADR-016:** Out-of-Band Remote Escalation (Telegram Bot HITL para autorização de PEP Level 2/3 com inatividade de terminal $> 180$s).

---

## 3. Divisão em Sprints & Entregáveis

| Sprint | Nome da Sprint | Objetivo Principal | Documento | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Sprint 1** | Main Timeline & SQLite FTS5 | Linha do tempo perpétua em SQLite WAL com busca BM25 sub-10ms e Day Markers | [`sprints/sprint-1.md`](sprints/sprint-1.md) | 📋 Planejado |
| **Sprint 2** | FastEmbed Local & RRF Fusion | Embeddings locais ONNX (`bge-small-en-v1.5`), deduplicação ($\ge 0.92$) e fusão RRF | [`sprints/sprint-2.md`](sprints/sprint-2.md) | 📋 Planejado |
| **Sprint 3** | The 5-Sphere Memory & Cognitive Tools | Perfil do Usuário ("Senhor", Maestria), Persona Dual (Daniel / Jarvis), Telemetria Host, Telegram HITL e Manifest | [`sprints/sprint-3.md`](sprints/sprint-3.md) | 📋 Planejado |
| **Sprint 4** | Universal Skills Standard & Compactor | Padrão `SKILL.md` com Progressive Disclosure, comando `/compact`, branches e checkpoints | [`sprints/sprint-4.md`](sprints/sprint-4.md) | 📋 Planejado |

---

## 4. Arquitetura Alvo & Componentes Afetados

```
src/orion/
├── memory/
│   ├── __init__.py
│   ├── models.py                      # FactEntry, FactStatus, UserProfile, ToolMastery, CognitiveManifest
│   ├── timeline.py                    # SQLite WAL FTS5 Timeline & DayMarkers
│   ├── vector_store.py                # FastEmbed ONNX local (bge-small-en-v1.5) & Cosine (dedup >= 0.92)
│   ├── facts_store.py                 # Fatos estruturados tipados com ciclo CONFIRMED/INFERRED/DEPRECATED
│   ├── hybrid_retriever.py            # Reciprocal Rank Fusion (RRF) com budget de 1500 tokens
│   ├── manifest.py                    # Gerador do Cognitive Manifest ultra-compacto (< 250 tokens)
│   ├── file_syncer.py                 # Sincronização de MEMORY.md (teto 200 linhas) e daily logs
│   ├── hitl_telegram.py               # Conector Out-of-Band Telegram Bot para aprovação PEP remota
│   └── tools.py                       # Ferramentas: memorize, recall, deprecate_fact, inspect_environment
├── runtime/
│   └── environment.py                 # Telemetria de hardware (psutil), display mode e Headroom Guard
├── core/
│   └── identity.py                    # Origem Imutável (Daniel/danielribeiro-dev) e Persona Engine (Jarvis)
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
            └── SKILL.md               # Skill nativa inicial de diagnóstico do SO
```

---

## 5. Matriz de Critérios de Aceite da Versão (DoD Global)

| ID | Cenário | Comportamento Esperado | Como Validar | Status |
|:---|:---|:---|:---|:---|
| CA-01 | Main Timeline & FTS5 | Eventos gravados em WAL com busca BM25 retornando em $< 10\text{ ms}$ | `pytest tests/unit/test_timeline.py` | ⏳ Pendente |
| CA-02 | FastEmbed Local & RRF | Embeddings ONNX gerados em CPU local sem PyTorch; deduplicação em $\ge 0.92$ | `pytest tests/unit/test_vector_store.py` | ⏳ Pendente |
| CA-03 | Blindagem Anti-Poisoning | Fatos inferidos nunca sobrescrevem regras confirmadas pelo usuário | `pytest tests/unit/test_facts_store.py` | ⏳ Pendente |
| CA-04 | Cognitive Manifest Budget | Bloco injetado no boot permanece rigorosamente abaixo de 250 tokens | `pytest tests/unit/test_manifest.py` | ⏳ Pendente |
| CA-05 | Environment Headroom Guard| Bloqueio proativo de navegadores se RAM livre $< 1.5\text{ GB}$ | `pytest tests/unit/test_environment.py` | ⏳ Pendente |
| CA-06 | Identidade Dual & Persona | Reconhece origem (Daniel Ribeiro) e assume persona Jarvis concisa/didática | `pytest tests/unit/test_identity.py` | ⏳ Pendente |
| CA-07 | Escalonamento Remoto HITL | Inatividade no terminal ($> 180$s) dispara aprovação no Telegram Bot | `pytest tests/unit/test_hitl_telegram.py` | ⏳ Pendente |
| CA-08 | Ferramentas Cognitivas | `memorize`, `recall`, `deprecate_fact`, `inspect_environment` no ReAct loop | `pytest tests/unit/test_memory_tools.py` | ⏳ Pendente |
| CA-09 | Progressive Skills Standard | Boot varre skills consumindo $< 100$ tokens/skill; `use_skill` carrega tudo | `pytest tests/unit/test_skills_loader.py` | ⏳ Pendente |
| CA-10 | Dynamic Compactor | Compacting automático a 80% do budget preserva *vital tail* e arquivos ativos | `pytest tests/unit/test_compactor.py` | ⏳ Pendente |
| CA-11 | Branches & Síntese | Merge de branch gera checkpoint conciso na Main Timeline | `pytest tests/unit/test_branches.py` | ⏳ Pendente |
| CA-12 | Cobertura de Testes | Suíte completa da v0.2.0 passando com cobertura global $\ge 85\%$ | `pytest --cov=src/orion` | ⏳ Pendente |

---

## 6. Checklist de Conclusão da Spec (Congelamento)

- [x] Especificação técnica e arquitetural da v0.2.0 alinhada e aprovada pelo usuário.
- [x] As 4 sprints da v0.2.0 devidamente atualizadas com as 5 Esferas Cognitivas, PCU e Remote HITL.
- [ ] Implementação de todas as 4 sprints concluída com testes automatizados.
- [ ] Bateria de testes com cobertura $\ge 85\%$.
- [ ] Tag Git `v0.2.0` criada.
