# O.R.I.O.N — Active Context (Memória de Sessão de Desenvolvimento)

> **Data de Atualização:** 24/10/2026  
> **Status Atual:** Fase 0 Concluída e Aprovada — Especificação e Alinhamento da v0.1.0 Fechados  
> **Regra Suprema:** Nenhuma linha de código em `src/` é escrita até o comando explícito de início da Sprint 1.

---

## 🎯 Foco Imediato & Estado de Alinhamento com o Usuário
1. **Decisões Estratégicas Consolidadas da v0.1.0 (Alinhamento Concluído):**
   - [x] **L60 — Soberania das Ferramentas Nativas:** O ORION não depende de muletas ou classes externas do Hermes. As 5 Primitivas Nativas (`run_command`, `read_file`, `write_file`, `edit_file` com correspondência exata de bloco, `search_files`) nascem puras no núcleo.
   - [x] **L68 — Action-Observation Event Stream:** Adoção formal do padrão de Event Stream imutável tipado com Pydantic v2 e controle de turn budgeting (teto de 20 voltas).
   - [x] **L78 — Consciência de Custos & Dynamic Auto-Routing:** Exibição de tokens e custos no CLI; modos automático e fixo; suporte aberto a OpenRouter e provedores diretos.
   - [x] **L81 — Subsistema de Artefatos com Persistência Dual:** Armazenamento global em `~/.orion/brain/<session_id>/artifacts/` e local em `.orion/artifacts/`.
   - [x] **L86 — Fechamento Documental:** Especificações da v0.1.0 congeladas.

2. **Planejamento Estratégico & Especificação Fechada da v0.2.0 (Superioridade Competitiva):**
   - [x] **Pesquisa de Mercado:** Benchmark aprofundado com Claude Code, Google Antigravity, OpenHands e Letta/MemGPT.
   - [x] **Pacto do Acrônimo O.R.I.O.N:** Cada letra do nome respaldada por arquitetura real.
   - [x] **Memória Tríplice Híbrida RRF:** SQLite WAL FTS5 BM25 + ONNX FastEmbed Local (`bge-small-en-v1.5`, < 130MB, sem PyTorch) + Fatos estruturados com ciclo anti-envenenamento (`CONFIRMED`, `INFERRED`, `DEPRECATED`) com injeção RRF limitada a 1.500 tokens.
   - [x] **Universal Agent Skills Standard (`SKILL.md`):** Padrão aberto da indústria com Divulgação Progressiva em 3 estágios e ferramenta `use_skill`.
   - [x] **Dynamic Context Compactor & Branches:** Auto-compaction automática silenciosa a 80% do budget de contexto (preservando *vital tail* e arquivos ativos), comando `/compact` e branches contextuais com síntese de checkpoints imutáveis.
   - [x] **Sprints da v0.2.0:** Todas as 4 sprints formalizadas em `docs/planning/versions/v0.2.0/sprints/` (`sprint-1.md` a `sprint-4.md`).

3. **Status do Projeto:**
   - Estamos na etapa rigorosa de planejamento e documentação prévia das versões. Nenhuma linha de código é escrita sem alinhamento.
   - v0.1.0 e v0.2.0 possuem especificações arquiteturais completas, templates de sprint e critérios de aceite detalhados.

---

## 📌 Próximo Passo
Apresentar a formalização documental da v0.2.0 concluída ao usuário e alinhar os próximos passos (ex: planejar a v0.3.0 Model Gateway & Offline Resilience ou avançar nas demais versões).
