# Sprint — [v0.1.0] Sprint 4: Testes Automatizados E2E & Release

> **Status:** 📋 Planejado  
> **Versão Relacionada:** v0.1.0 (Clean Foundation & Core ReAct Engine)  
> **Responsável / Agente:** Daniel Dev & Antigravity  
> **Data de Início:** A definir  
> **Data de Conclusão:** —  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Integrar todos os módulos desenvolvidos nas Sprints 1, 2 e 3 em um fluxo ponta a ponta (**End-to-End**), construir o harness de testes automatizados, garantir cobertura superior a 85%, validar a auditoria de segurança e formalizar a release `v0.1.0`.
* **Dependências Prévias:** Sprints 1, 2 e 3 concluídas com sucesso.
* **Entregável Verificável:** O comando `pytest --cov=src/orion` executando 100% verde com cobertura $\ge 85\%$, documentação de release congelada e repositório tagueado com `v0.1.0`.

---

## 2. Contexto de Engenharia

* **Por que esta sprint existe:** Para garantir que a v0.1.0 seja uma base de rocha sólida, sem dívidas técnicas ocultas, pronta para que novos contribuidores possam clonar o repositório e confiar na suíte de testes antes de adicionarmos a Memória Tríplice na v0.2.0.

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Estado Inicial | Estado Final Esperado (DoD) |
| :--- | :--- | :--- |
| **Integração E2E** | Módulos testados apenas em isolamento | Cenários completos do ReAct ao Runtime testados |
| **Cobertura de Código** | Parcial por módulo | Cobertura global verificada $\ge 85\%$ |
| **Release** | Não versionada formalmente | Tag Git `v0.1.0` criada e spec congelada |

---

## 4. Escopo da Sprint

### ✅ No Escopo (In Scope)
- [ ] Implementação de testes E2E em `tests/e2e/test_react_flow.py` (simulação de prompt com leitura de arquivo e resposta final).
- [ ] Teste de auditoria de segurança em `tests/e2e/test_security_audit.py` (tentativa de bypass do PEP e injeção de prompt).
- [ ] Medição formal de cobertura via `pytest-cov` e validação da meta de 85%.
- [ ] Atualização do `README.md` com instruções reais de execução e teste.
- [ ] Congelamento da spec `docs/planning/versions/v0.1.0/VERSION.md` e criação da tag Git `v0.1.0`.

---

## 5. Arquitetura & Arquivos Afetados

```
tests/e2e/
  ├── __init__.py
  ├── test_react_flow.py
  └── test_security_audit.py
docs/planning/versions/v0.1.0/
  └── VERSION.md
```

---

## 6. Definition of Done (DoD)

- [ ] Suíte de testes completa executando com `pytest tests/`.
- [ ] Cobertura de código comprovada $\ge 85\%$.
- [ ] Nenhuma vulnerabilidade de segurança encontrada na auditoria estática.
- [ ] Tag `v0.1.0` registrada no Git.
- [ ] `.claudex/progress.md` e `.claudex/active_context.md` atualizados para o planejamento da v0.2.0.
