# O.R.I.O.N — Active Context (Memória de Sessão de Desenvolvimento)

> **Data de Atualização:** 24/10/2026  
> **Status Atual:** Fase 0 Concluída e Aprovada — Especificação e Alinhamento da v0.1.0 Fechados  
> **Regra Suprema:** Nenhuma linha de código em `src/` é escrita até o comando explícito de início da Sprint 1.

---

## 🎯 Foco Imediato & Estado de Alinhamento com o Usuário
1. **Decisões Estratégicas Consolidadas da v0.1.0 (Alinhamento Concluído):**
   - [x] **L60 — Soberania das Ferramentas Nativas:** O ORION não depende de muletas ou classes externas do Hermes. As 5 Primitivas Nativas (`run_command`, `read_file`, `write_file`, `edit_file` com correspondência exata de bloco, `search_files`) nascem puras no núcleo.
   - [x] **L68 — Action-Observation Event Stream:** Adoção formal do padrão de Event Stream imutável tipado com Pydantic v2 e controle de turn budgeting (teto de 20 voltas).
   - [x] **L78 — Consciência de Custos & Dynamic Auto-Routing:**
     - Exibição de tokens e custos no CLI durante ou ao final de turnos (estilo Claude Code).
     - Modos de operação configuráveis via `/config` ou linguagem natural por chat:
       1. *Modo Automático:* O ORION avalia a complexidade do passo e escala autonomamente para modelos de grande raciocínio (Claude 3.7 Sonnet / Opus / Gemini Pro) em etapas pesadas de arquitetura/planejamento, retornando para modelos rápidos de execução (Gemini Flash / Qwen Coder) nas etapas operacionais.
       2. *Modo Fixo:* O usuário fixa um modelo específico de sua preferência.
     - Suporte nativo a OpenRouter para ampla seleção de modelos.
   - [x] **L81 — Subsistema de Artefatos com Persistência Dual:** Armazenamento global em `~/.orion/brain/<session_id>/artifacts/` e local em `.orion/artifacts/` dentro de repositórios ativos.
   - [x] **L86 — Fechamento Documental:** Toda a documentação e planejamento mestre foram atualizados e sincronizados. Nenhuma linha de código foi implementada antecipadamente.

2. **Status de Prontidão da v0.1.0:**
   - A especificação mestre (`docs/planning/versions/v0.1.0/VERSION.md`) e suas 4 sprints (`sprint-1.md` a `sprint-4.md`) estão 100% definidas e fechadas.
   - O projeto está pronto para iniciar a **Sprint 1 (Tooling, Tipagem & Skeleton)** assim que o usuário solicitar.

---

## 📌 Próximo Passo
Aguardar autorização do usuário para iniciar a execução da **Sprint 1 da v0.1.0** (configuração de `pyproject.toml`, skeleton do CLI, Rich e modelos de tipagem Pydantic v2).
