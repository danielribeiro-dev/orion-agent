# Sprint — v0.5.0 Sprint 0: Higiene & Fundação

> **Status:** ✅ Concluída (merge/tags e turno real pendentes, ver abaixo)  
> **Versão Relacionada:** v0.5.0  
> **Responsável / Agente:** Daniel Dev & Claude  
> **Data de Início:** 2026-11-06  
> **Data de Conclusão:** 2026-11-06  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Fechar a v0.4.0, alinhar a documentação com o código e registrar os ADRs que governam a v0.5.0, medindo um baseline real antes de mexer no núcleo.
* **Dependências Prévias:** v0.4.0 Sprint 5 commitada (`ded03f4`).
* **Entregável Verificável:** docs consistentes, `CLAUDE.md` criado, ADR-020/021/022 registrados, relatório de baseline com provedor real.

---

## 2. Contexto de Engenharia

* **Por que esta sprint existe:** a documentação diverge do código (Sprint 5 commitada mas marcada como planejada; contagem de testes e de slash commands inconsistente; ADRs 014–018 duplicados) e nunca houve um turno com provedor real.
* **Como se encaixa:** é a base Doc-First da v0.5.0; sem baseline não há como medir ganho de tokens nem regressão.
* **Decisões associadas:** ADR-020, ADR-021, ADR-022 (novos).

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Estado Inicial | Estado Final (DoD) |
| :--- | :--- | :--- |
| **Docs** | `active_context`, `progress`, ROADMAP, README desatualizados | Consistentes com o código |
| **Git** | Tags só `v0.1.0`/`v0.2.0`; v0.4.0 não mesclada | Tags `v0.3.0`/`v0.4.0` e merge (com aprovação explícita do Senhor) |
| **Projeto** | Sem `CLAUDE.md` | `CLAUDE.md` com convenções |
| **Baseline** | Sem turno real | Relatório de 1 turno real + bugs registrados |

---

## 4. Escopo da Sprint

### ✅ No Escopo
- [x] Corrigir `.claudex/active_context.md`, `progress.md`, ROADMAP, README, contagens de testes/slash commands.
- [x] Desambiguar ADRs duplicados (014–018) em `.claudex/decisions.md` com sufixo `[vX.Y.Z]`.
- [x] Registrar ADR-020, ADR-021, ADR-022 e atualizar `docs/planning/versions/v1.6.0/VERSION.md` (escopo movido).
- [x] Criar `CLAUDE.md` na raiz.
- [x] Rodar a suíte completa e registrar números reais (testes, cobertura).
- [~] Turno real: não executado (sem chave de API nem Ollama no ambiente); baseline da suíte registrado em `baseline.md`. Passa para a Sprint 1.
- [ ] (pendente, aguarda autorização) Merge `version/v0.4.0` → `main` e tags `v0.3.0`/`v0.4.0` (somente com autorização do Senhor).

### 🚫 Fora de Escopo
- Qualquer alteração em `src/`, exceto correções triviais de bug bloqueantes encontradas no baseline (registradas à parte).

---

## 5. Arquitetura & Arquivos Afetados

```
CLAUDE.md                                         [novo]
.claudex/{active_context,progress,decisions}.md   [mod]
docs/planning/ROADMAP.md, README.md               [mod]
docs/planning/versions/v1.6.0/VERSION.md          [mod]
docs/planning/versions/v0.5.0/baseline.md         [novo]
```

---

## 6. Contratos de Código & Tipagem
Nenhum (sprint de documentação).

---

## 7. Estratégia de Implementação

1. Rodar `pytest tests/ --cov=src/orion` e anotar números reais.
2. Reconciliar docs com o código e com esses números.
3. Registrar ADRs 020–022 e renumerar duplicados.
4. Criar `CLAUDE.md`.
5. Turno real com OpenRouter; registrar bugs.
6. Com autorização, merge e tags.

---

## 8. Testes & Critérios de Aceite (DoD)

- [x] Suíte existente verde (1119 testes, 93,70%).
- [x] Nenhum doc afirma algo contrário ao código.
- [x] Baseline registrado (sem turno real).
- [x] `.claudex/progress.md` atualizado.

---

## 9. Critérios de Parada

1. Qualquer operação em `main`/tags exige confirmação explícita do Senhor.
2. Se o baseline revelar falha estrutural que muda o escopo das Sprints 1–2, pausar para revisão.
