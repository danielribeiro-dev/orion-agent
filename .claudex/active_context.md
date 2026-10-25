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
   - [x] **Memória Tríplice Híbrida RRF:** SQLite WAL FTS5 BM25 + ONNX FastEmbed Local (`bge-small-en-v1.5`) + Fatos estruturados anti-envenenamento (< 1.500 tokens).
   - [x] **Universal Agent Skills Standard (`SKILL.md`):** Divulgação Progressiva em 3 estágios e ferramenta `use_skill`.
   - [x] **Dynamic Context Compactor & Branches:** Auto-compaction a 80%, comando `/compact` e branches com síntese de checkpoints.
   - [x] **Sprints da v0.2.0:** Todas as 4 sprints formalizadas em `docs/planning/versions/v0.2.0/sprints/`.

3. **Planejamento Estratégico & Especificação Fechada da v0.4.0 (Padrão Claude Code & Antigravity):**
   - [x] **Comando Oficial `orion-agent`:** O Stream CLI diário é invocado por `orion-agent`; o comando `orion` fica reservado para a interface eDEX/Desktop pós-v1.0.0.
   - [x] **Stack Stream CLI:** `prompt_toolkit` (Buffer, histórico, autocomplete `/` e `@`) + `Rich` (Streaming `Live`, diffs cirúrgicos e banner adaptativo da Mão Cósmica com Buraco Negro).
   - [x] **Catálogo Oficial dos 20 Slash Commands:** Comandos cognitivos, de memória, branches, operação e custos.
   - [x] **Cliente Nativo MCP:** Suporte a stdio e SSE com interceptação determinística pelo PEP.
   - [x] **Sprints da v0.4.0:** Todas as 4 sprints formalizadas em `docs/planning/versions/v0.4.0/sprints/`.

4. **Status do Projeto:**
   - Estamos na etapa rigorosa de planejamento e documentação prévia das versões. Nenhuma linha de código em `src/` é escrita sem alinhamento.
   - v0.1.0, v0.2.0 e v0.4.0 possuem especificações completas, templates de sprint e critérios de aceite detalhados.

---

## 📌 Próximo Passo
Apresentar a formalização documental da v0.4.0 concluída ao usuário e alinhar os próximos passos (ex: planejar a v0.3.0 Model Gateway, Real-Time Cost Ledger & Offline Resilience).
