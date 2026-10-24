# Sprint — [v0.1.0] Sprint 3: PEP Governance & RuntimeProvider

> **Status:** 📋 Planejado  
> **Versão Relacionada:** v0.1.0 (Clean Foundation & Core ReAct Engine)  
> **Responsável / Agente:** Daniel Dev & Antigravity  
> **Data de Início:** A definir  
> **Data de Conclusão:** —  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Construir a camada de governança e segurança determinística (**Policy Enforcement Point - PEP**), a interface abstrata `RuntimeProvider` (separação rígida Brain × Body) e o adaptador isolado do Hermes Agent (`HermesBridge`), permitindo que o ReAct Engine execute ações reais com autorização humana explícita.
* **Dependências Prévias:** Sprint 2 concluída com sucesso.
* **Entregável Verificável:** O agente consegue receber uma solicitação que exige ler arquivos ou rodar comandos shell, o PEP intercepta a ação, solicita confirmação no modo supervisionado, e o `RuntimeProvider` executa e retorna o `RuntimeResult` padronizado.

---

## 2. Contexto de Engenharia

* **Por que esta sprint existe:** Para garantir a regra inviolável do ORION: *"O LLM nunca acessa o sistema operacional diretamente"*. Todo I/O passa pelo contrato `RuntimeProvider` e pelo PEP, blindando o computador contra alucinações destrutivas.
* **Decisões associadas:** Especificações [`GOVERNANCE_PEP.md`](../../../architecture/GOVERNANCE_PEP.md) e [`CORE_REACT_ENGINE.md`](../../../architecture/CORE_REACT_ENGINE.md).

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Estado Inicial | Estado Final Esperado (DoD) |
| :--- | :--- | :--- |
| **Governança** | Inexistente | `PolicyEnforcementPoint` com `ActionLevel` (0 a 3) e modo supervisionado |
| **I/O do SO** | Inexistente | `RuntimeProvider` (ABC) isolando comandos shell e arquivos |
| **Hermes Bridge** | Inexistente | Módulo isolado chamando tools do Hermes sem expor código alheio |

---

## 4. Escopo da Sprint

### ✅ No Escopo (In Scope)
- [ ] Implementação de `src/orion/governance/permissions.py` (Enums `ActionLevel`: LEVEL_0 informativo, LEVEL_1 leitura, LEVEL_2 mutação simples, LEVEL_3 crítico de sistema).
- [ ] Implementação de `src/orion/governance/pep.py` (Validador de políticas que aprova ou barra ações de acordo com o modo de autonomia).
- [ ] Implementação de `src/orion/governance/audit.py` (Log append-only em `~/.orion/audit.log`).
- [ ] Implementação de `src/orion/runtime/provider.py` (Classe abstrata `RuntimeProvider` e dataclass `RuntimeResult`).
- [ ] Implementação de `src/orion/runtime/hermes_bridge.py` (Adaptador de transição para o Hermes Agent, chamando apenas suas tools de baixo nível via subprocess/função standalone).
- [ ] Testes unitários do PEP simulando negações de permissão e auditoria.

### 🚫 Fora de Escopo (Out of Scope / Anti-Metas)
- Não acoplar inteligência ou loop do Hermes (apenas as ferramentas puras de I/O são utilizadas).
- Não criar clientes MCP nesta sprint (escopo da v0.4.0).

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/
  ├── governance/
  │   ├── __init__.py
  │   ├── permissions.py
  │   ├── pep.py
  │   └── audit.py
  └── runtime/
      ├── __init__.py
      ├── provider.py
      └── hermes_bridge.py
tests/unit/
  ├── test_pep.py
  └── test_runtime_provider.py
```

---

## 6. Definition of Done (DoD)

- [ ] Ações destrutivas (LEVEL 2 e 3) não conseguem ser executadas sem autorização do PEP.
- [ ] Nenhuma chamada de `subprocess` ou `os.system` existe fora de `src/orion/runtime/`.
- [ ] O `RuntimeResult` normaliza saídas com `success`, `data`, `error` e `meta`.
- [ ] Testes de permissão e runtime passam com 100% de sucesso.
- [ ] `.claudex/progress.md` atualizado.
