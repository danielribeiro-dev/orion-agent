# Spec — [v0.1.0] Clean Foundation & Core ReAct Engine

> **Status:** 🔄 Especificação Finalizada e Fechada para Início da Sprint 1  
> **Criada em:** 2026-10-24  
> **Concluída em:** —  
> **Autor(es):** Daniel Dev & Antigravity (Pair Programming)  
> **Branch:** `main`  

---

## 1. Visão Geral & Motivação

### 1.1 Objetivo
Estabelecer a fundação 100% limpa, modular e testada do **O.R.I.O.N (Operational Reasoning & Intelligence Orchestration Network)**, construindo:
1. O **Core ReAct Loop assíncrono** orientado ao padrão **Action-Observation Event Stream** com controle estrito de voltas (*Turn Budgeting*).
2. O **Policy Enforcement Point (PEP)** determinístico operando sob o princípio *Deny by Default* com 4 níveis estritos de permissão (LEVEL_0 a LEVEL_3).
3. As **5 Ferramentas Primitivas Nativas** de nível mundial (`run_command`, `read_file`, `write_file`, `edit_file` com correspondência exata de bloco e `search_files`), garantindo soberania total sem muletas externas.
4. O **Subsistema de Artefatos Estruturados** (`ArtifactStore`) com suporte dual de armazenamento (`~/.orion/` global e `.orion/` local) e metadados (`RequestFeedback`, `Summary`, `UserFacing`).
5. A infraestrutura de CLI rica (Rich/Typer) com exibição do banner ASCII *The Hunter Crest*, acompanhamento de tokens em tempo real e preparação de esquemas de configuração (`auto` vs `fixed`).

### 1.2 Por que agora?
Para fazer jus ao nome O.R.I.O.N desde a primeira linha de código, o sistema precisa nascer com arquitetura superior aos benchmarks de mercado (Claude Code, Antigravity, OpenHands, Aider). Não podemos depender de classes ou scripts monolíticos de terceiros para I/O básico.

### 1.3 O que NÃO é escopo (anti-metas)
- Não implementar Memória Tríplice ou Linha do Tempo em SQLite FTS5/ONNX nesta versão (escopo da v0.2.0).
- Não plugar hardware de voz ou áudio (escopo da v0.5.0).
- Não criar clientes MCP externos nesta versão (escopo da v0.4.0).

---

## 2. Decisões Arquiteturais & Diretrizes de Design (ADRs)

- **ADR-001:** Repositório novo limpo `orion-agent` sem reaproveitamento cego de código legado.
- **ADR-002:** Núcleo aberto sem serviços proprietários hardcodados.
- **ADR-003:** Presença ambiente headless de voz e TUI sob demanda.
- **ADR-004:** Memória Tríplice (v0.2.0).
- **ADR-005:** Soberania Operacional: 5 Ferramentas Primitivas Nativas puras no `LocalRuntimeProvider`, tornando o Hermes apenas um adaptador secundário plugável.
- **ADR-006:** Modo supervisionado inicial com PEP estrito (confirmação `[Y/n]` para mutações de arquivos e comandos de shell).
- **ADR-007:** Alinhamento documental prévio obrigatório (Doc-First Engineering).
- **ADR-008:** Paradigma Action-Observation Event Stream imutável com Pydantic v2 e subsistema de Artefatos com persistência dual.
- **ADR-009:** Consciência de Tokens e Custos no CLI com suporte a modos `auto` (Dynamic Auto-Routing) e `fixed` no Gateway.

---

## 3. Divisão em Sprints & Entregáveis

| Sprint | Nome da Sprint | Objetivo Principal | Documento | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Sprint 1** | Tooling, Tipagem & Skeleton | `pyproject.toml`, Pydantic v2, CLI Skeleton, Banner Hunter Crest e Esquemas de Configuração | [`sprints/sprint-1.md`](sprints/sprint-1.md) | ✅ Concluída |
| **Sprint 2** | Core ReAct Engine & Action-Observation EventBus | Loop assíncrono, State Machine, Delimitadores Formais e Subsistema de Artefatos | [`sprints/sprint-2.md`](sprints/sprint-2.md) | ✅ Concluída |
| **Sprint 3** | As 5 Primitivas Nativas & PEP Determinístico | `run_command`, `read_file`, `write_file`, `edit_file`, `search_files`, LocalRuntimeProvider e PEP (Níveis 0 a 3) | [`sprints/sprint-3.md`](sprints/sprint-3.md) | 📋 Planejado |
| **Sprint 4** | Testes Automatizados E2E, Cobertura $\ge 85\%$ & Release | Integração E2E ponta a ponta, auditoria de segurança estática/dinâmica e congelamento da v0.1.0 | [`sprints/sprint-4.md`](sprints/sprint-4.md) | 📋 Planejado |

---

## 4. Arquitetura Alvo & Componentes Afetados

```
src/orion/
├── __init__.py                        # __version__ = "0.1.0-alpha"
├── cli.py                             # Entrypoint CLI (orion --version, orion chat)
├── config.py                          # Configurações do sistema (modos auto/fixed, providers, paths)
├── core/
│   ├── __init__.py
│   ├── state.py                       # State Machine (IDLE, REASONING, ACTION_PENDING, etc.)
│   ├── events.py                      # Modelos imutáveis Action, Observation, TurnEvents
│   ├── event_bus.py                   # Pub/Sub assíncrono in-process com histórico circular
│   ├── errors.py                      # Hierarquia de exceções de domínio tipadas
│   └── engine.py                      # ReAct Engine com Turn Budgeting (max_turns=20)
├── governance/
│   ├── __init__.py
│   ├── permissions.py                 # Enums ActionLevel (LEVEL_0 a LEVEL_3) e WorkspaceScope
│   ├── pep.py                         # Policy Enforcement Point determinístico
│   └── audit.py                       # AuditLogger append-only com timestamp e integridade
├── runtime/
│   ├── __init__.py
│   ├── provider.py                    # Classe abstrata BaseRuntimeProvider & RuntimeResult
│   ├── local_provider.py              # Provider nativo que executa ferramentas no SO
│   └── tools/                         # As 5 Ferramentas Primitivas Nativas
│       ├── __init__.py
│       ├── base.py                    # BaseTool com contrato schema Pydantic v2
│       ├── run_command.py             # Shell assíncrono com timeout, output limit e background tracking
│       ├── read_file.py               # Leitura com offsets de linha e proteção de contexto
│       ├── write_file.py              # Gravação atômica segura
│       ├── edit_file.py               # Exact-Match Anchored String Replacement
│       └── search_files.py            # Glob e Grep com filtros de ignore
└── artifacts/
    ├── __init__.py
    ├── models.py                      # Metadados de artefatos (ArtifactMetadata, Summary, RequestFeedback)
    └── store.py                       # Gerenciador de persistência dual (~/.orion/ e .orion/)
tests/
├── conftest.py                        # Fixtures assíncronas e mocks de inferência
├── unit/
│   ├── test_cli.py
│   ├── test_config.py
│   ├── test_engine.py
│   ├── test_event_bus.py
│   ├── test_pep.py
│   ├── test_tools.py
│   └── test_artifacts.py
└── e2e/
    ├── test_react_flow.py             # Cenários de ponta a ponta
    └── test_security_audit.py         # Testes de bypass de PEP e injeção de prompt
```

---

## 5. Matriz de Critérios de Aceite da Versão (DoD Global)

| ID | Cenário | Comportamento Esperado | Como Validar | Status |
|:---|:---|:---|:---|:---|
| CA-01 | Instalação & Setup | Instalação limpa via `pip install -e .` ou `uv pip install -e .` sem erros | `orion --version` | ⏳ Pendente |
| CA-02 | Core ReAct Loop | Recebe intenção, orquestra ciclo Action-Observation e encerra com `max_turns` | `pytest tests/unit/test_engine.py` | ⏳ Pendente |
| CA-03 | Blindagem de Governança | Toda ferramenta mutante é barrada pelo PEP no modo supervisionado até autorização | `pytest tests/unit/test_pep.py` | ⏳ Pendente |
| CA-04 | Ferramentas Nativas Puras | Leitura, edição cirúrgica por exatidão de bloco e execução de shell rodam sem Hermes | `pytest tests/unit/test_tools.py` | ⏳ Pendente |
| CA-05 | Subsistema de Artefatos | Planos e relatórios estruturados são salvos no local correto com metadados | `pytest tests/unit/test_artifacts.py` | ⏳ Pendente |
| CA-06 | Qualidade & Cobertura | 100% dos testes passando com cobertura superior a 85% | `pytest --cov=src/orion` | ⏳ Pendente |

---

## 6. Checklist de Conclusão da Spec (Congelamento)

- [x] Especificação técnica da v0.1.0 validada e alinhada com o usuário.
- [ ] Todas as 4 sprints da v0.1.0 concluídas e aprovadas.
- [ ] Bateria de testes automatizados com cobertura $\ge 85\%$.
- [ ] Atualização de `.claudex/progress.md` e `.claudex/active_context.md`.
- [ ] Tag Git `v0.1.0` criada.
