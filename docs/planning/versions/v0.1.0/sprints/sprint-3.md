# Sprint — [v0.1.0] Sprint 3: As 5 Primitivas Nativas & PEP Determinístico

> **Status:** ✅ Concluída  
> **Versão Relacionada:** v0.1.0 (Clean Foundation & Core ReAct Engine)  
> **Responsável / Agente:** Daniel Dev & Antigravity  
> **Data de Início:** 2026-10-24  
> **Data de Conclusão:** 2026-10-24  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Construir a camada de governança determinística (**Policy Enforcement Point - PEP**), a interface `BaseRuntimeProvider` e as **5 Ferramentas Primitivas Nativas** de manipulação de sistema operacional e código (`run_command`, `read_file`, `write_file`, `edit_file` com correspondência exata de bloco e `search_files`), garantindo que o O.R.I.O.N execute ações reais com soberania total e sem dependência obrigatória de ferramentas externas.
* **Dependências Prévias:** Sprint 2 concluída com sucesso.
* **Entregável Verificável:** O agente é capaz de ler arquivos, pesquisar termos no repositório, aplicar edições cirúrgicas e rodar comandos shell de forma segura, com o PEP interceptando toda mutação e registrando auditoria no `audit.log`.

---

## 2. Contexto de Engenharia

* **Por que esta sprint existe:** Para honrar a regra suprema de segurança: *"O cérebro da IA nunca toca o sistema operacional diretamente"*. Ao mesmo tempo, inspirando-se no padrão consagrado do Claude Code e Antigravity, as ferramentas de manipulação de código devem operar por ancoragem de correspondência exata de bloco (`exact string target replacement`), evitando diffs quebrados ou alucinações de reescrita total.
* **Decisões associadas:** [`GOVERNANCE_PEP.md`](../../../architecture/GOVERNANCE_PEP.md), ADR-005 e ADR-006.

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Estado Inicial | Estado Final Esperado (DoD) |
| :--- | :--- | :--- |
| **Governança** | Inexistente | `PolicyEnforcementPoint` determinístico com `ActionLevel` (0 a 3) e modo supervisionado |
| **Auditoria** | Inexistente | `AuditLogger` gravando log append-only com hash e timestamp |
| **I/O do SO** | Inexistente | `LocalRuntimeProvider` e contrato `BaseRuntimeProvider` desacoplado |
| **Manipulação de Código** | Inexistente | `edit_file` cirúrgico por correspondência exata de bloco com checagem de unicidade |
| **Shell & Busca** | Inexistente | `run_command` com timeout e `search_files` com glob/grep rápidos |

---

## 4. Escopo da Sprint

### ✅ No Escopo (In Scope)
- [x] Implementação de `src/orion/governance/permissions.py`:
  - `ActionLevel` Enum (`LEVEL_0` informativo, `LEVEL_1` leitura passiva, `LEVEL_2` mutação dentro do workspace, `LEVEL_3` crítico de sistema).
  - `WorkspaceScope` para delimitar caminhos autorizados no sistema de arquivos.
- [x] Implementação de `src/orion/governance/pep.py`:
  - Interceptor síncrono/assíncrono de instâncias de `Action`.
  - Validador de risco e gatekeeper de confirmação no Modo Supervisionado (`[Y/n]`).
- [x] Implementação de `src/orion/governance/audit.py`:
  - `AuditLogger` gravando eventos em `~/.orion/audit.log` (timestamp, tool, params, authorized, status).
- [x] Implementação de `src/orion/runtime/provider.py` (`BaseRuntimeProvider` e `RuntimeResult`).
- [x] Implementação de `src/orion/runtime/local_provider.py` (Orquestrador de execução de tools locais).
- [x] Implementação das **5 Ferramentas Primitivas Nativas** em `src/orion/runtime/tools/`:
  - `run_command.py`: Shell assíncrono via `asyncio.subprocess` com timeout, limite de buffer e captura de saída.
  - `read_file.py`: Leitura com paginação por offsets de linha e limite de bytes.
  - `write_file.py`: Gravação atômica via tempfile + `os.replace` para integridade de arquivo.
  - `edit_file.py`: Substituição cirúrgica exata (`target` -> `replacement`) com exigência de ocorrência única.
  - `search_files.py`: Glob de arquivos e Grep de expressões regulares com exclusão de pastas ignoradas (`.git`, `__pycache__`, `node_modules`).
- [x] Testes unitários do PEP (aprovações, negações) e testes funcionais de cada uma das 5 ferramentas primitivas.

### 🚫 Fora de Escopo (Out of Scope / Anti-Metas)
- Não construir cliente MCP (escopo da v0.4.0).
- Não criar sandbox com Bubblewrap nesta sprint (escopo da v1.5.0).

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
    ├── local_provider.py
    └── tools/
        ├── __init__.py
        ├── base.py
        ├── run_command.py
        ├── read_file.py
        ├── write_file.py
        ├── edit_file.py
        └── search_files.py
tests/unit/
├── test_pep.py
└── test_tools.py
```

---

## 6. Definition of Done (DoD)

- [x] Ações mutantes (`LEVEL_2` e `LEVEL_3`) não executam no Modo Supervisionado sem aprovação do PEP.
- [x] Nenhuma chamada de `subprocess` ou `os.system` existe fora do runtime nativo.
- [x] `edit_file` falha de forma segura caso o bloco de destino não seja único no arquivo.
- [x] `run_command` respeita timeouts e mata processos filhos travados.
- [x] Todas as ações sensíveis são registradas de forma append-only no `audit.log`.
- [x] Testes unitários de `test_pep.py` e `test_tools.py` passam com 100% de sucesso.
- [x] Suite completa: **168 testes passando** com cobertura de **92.46%** (meta: ≥85%)..
