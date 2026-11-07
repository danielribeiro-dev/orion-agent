# Sprint — v0.5.0 Sprint 8: Hardening & Release

> **Status:** 📋 Planejando  
> **Versão Relacionada:** v0.5.0  
> **Responsável / Agente:** Daniel Dev & Claude (via ORION)  
> **Data de Início:** —  
> **Data de Conclusão:** —  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Provar a paridade com o Claude Code, endurecer segurança e custo, e liberar a v0.5.0.
* **Dependências Prévias:** Sprints 0–7.
* **Entregável Verificável:** checklist de paridade 100% verde, evals reproduzíveis, tag `v0.5.0`.

---

## 2. Contexto de Engenharia

* **Por que existe:** o ORION agora executa código real, fala com a rede e roda sozinho; a versão só fecha com evidência de segurança, custo e paridade.

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Antes | Depois |
| :--- | :--- | :--- |
| **Paridade** | Sem medição | Checklist com ~30 capacidades, cada uma com teste/eval |
| **Evals** | Só A/B de MCP parcial | bugfix, refactor, feature pequena com custo/turnos/acerto |
| **Segurança** | Suíte da v0.4.0 | + injeção via tool_result/web/MCP, escalada por subagent/hook, socket do daemon |
| **Operação** | `orion doctor` básico | Chave, provider, MCPs, daemon, schedules |

---

## 4. Escopo da Sprint

### ✅ No Escopo
- [ ] Suíte e relatório de paridade em `docs/planning/versions/v0.5.0/parity.md`.
- [ ] Evals de tarefas reais e meta de ≥ 25% menos tokens que o baseline (cache + MCP lazy).
- [ ] Fuzz do parser SSE; testes de segurança listados acima.
- [ ] `orion doctor` completo; migração dos `sessions.db`/`memory.db` órfãos em `~/.orion`.
- [ ] CHANGELOG, docs de usuário, atualização de `.claudex/`, tag `v0.5.0` (com autorização).

### 🚫 Fora de Escopo
- Voz, desktop, sandbox, self-healing.

---

## 5. Arquitetura & Arquivos Afetados

```
tests/parity/ tests/evals/ tests/security/   [novo]
src/orion/cli.py (doctor)                    [mod]
CHANGELOG.md, docs/                          [novo/mod]
```

---

## 6. Contratos de Código & Tipagem
Nenhum contrato novo.

---

## 7. Estratégia de Implementação

1. Montar checklist de paridade e automatizar o que for possível.
2. Evals com baseline da Sprint 0.
3. Segurança e fuzz.
4. Doctor, migração, docs.
5. Congelamento e tag.

---

## 8. Testes & Critérios de Aceite (DoD)

- Todos os CA-01…CA-12 de `VERSION.md` validados.
- Uma semana de uso diário pelo ORION sem regressão crítica.
- [ ] mypy/ruff limpos; cobertura ≥ 85%; `.claudex/progress.md` atualizado.

---

## 9. Critérios de Parada

1. Qualquer CA de segurança falhando.
2. Tag e merge em `main` somente com confirmação explícita do Senhor.
