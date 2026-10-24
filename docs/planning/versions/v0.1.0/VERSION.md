# Spec — [v0.1.0] Clean Foundation & Core ReAct Engine

> **Status:** 🔄 Em Execução  
> **Criada em:** 2026-10-24  
> **Concluída em:** —  
> **Autor(es):** Daniel Dev & Antigravity (Pair Programming)  
> **Branch:** `main`  

---

## 1. Visão Geral & Motivação

### 1.1 Objetivo
Estabelecer a fundação 100% limpa, modular e testada do **ORION-Agent**, construindo o **Core ReAct Loop assíncrono**, a máquina de estados de raciocínio, o **Policy Enforcement Point (PEP)** para governança de segurança determinística, e o **RuntimeProvider** com a ponte de isolamento do Hermes Agent.

### 1.2 Por que agora?
O repositório legado continha ideias de alto valor intelectual, mas com acoplamento a padrões antigos (intents rígidos) e dependências parciais. Esta versão estabelece a linha de partida limpa (Clean Slate), garantindo que qualquer desenvolvedor ou colaborador da comunidade consiga executar, entender e estender o ORION.

### 1.3 O que NÃO é escopo (anti-metas)
- Não implementar Memória Tríplice ou Linha do Tempo persistente nesta versão (escopo exclusivo da v0.2.0).
- Não plugar hardware de voz ou áudio (escopo da v0.5.0).
- Não acoplar ferramentas proprietárias de empresas ou projetos específicos.

---

## 2. Decisões Arquiteturais & Diretrizes de Design

- **ADR-001:** Repositório novo limpo `orion-agent` sem reaproveitamento cego de código legado.
- **ADR-002:** Núcleo aberto sem serviços proprietários hardcodados.
- **ADR-003:** Presença ambiente headless de voz e TUI sob demanda.
- **ADR-005:** Hermes como provider de transição estritamente isolado atrás de `RuntimeProvider`.
- **ADR-006:** Modo supervisionado inicial com PEP estrito (confirmação `[Y/n]` para ações modificadoras).
- **ADR-007:** Alinhamento documental prévio obrigatório (Doc-First Engineering).

---

## 3. Divisão em Sprints & Entregáveis

| Sprint | Nome da Sprint | Objetivo Principal | Documento | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Sprint 1** | Tooling, Tipagem & Skeleton | `pyproject.toml`, Pydantic v2, CLI Skeleton e Rich | [`sprints/sprint-1.md`](sprints/sprint-1.md) | 📋 Planejado |
| **Sprint 2** | Core ReAct Engine & EventBus | Loop assíncrono, State Machine e Delimitadores | [`sprints/sprint-2.md`](sprints/sprint-2.md) | 📋 Planejado |
| **Sprint 3** | PEP Governance & RuntimeProvider | Policy Enforcement Point e Hermes Bridge de I/O | [`sprints/sprint-3.md`](sprints/sprint-3.md) | 📋 Planejado |
| **Sprint 4** | Testes Automatizados E2E & Release | Suíte de testes com cobertura 85%+ e empacotamento | [`sprints/sprint-4.md`](sprints/sprint-4.md) | 📋 Planejado |

---

## 4. Arquitetura Alvo & Componentes Afetados

```
src/orion/
  ├── __init__.py
  ├── cli.py                         # Ponto de entrada CLI (orion --help, orion chat)
  ├── core/
  │   ├── engine.py                  # Loop ReAct assíncrono e State Machine
  │   ├── event_bus.py               # Pub/sub interno de eventos tipados
  │   └── errors.py                  # Hierarquia de exceções de domínio
  ├── governance/
  │   ├── pep.py                     # Policy Enforcement Point
  │   ├── permissions.py             # ActionLevels (LEVEL_0 a LEVEL_3) e Roles
  │   └── audit.py                   # AuditLogger append-only
  └── runtime/
      ├── provider.py                # Interface abstrata RuntimeProvider & RuntimeResult
      └── hermes_bridge.py           # Adaptador desacoplado do Hermes Agent
tests/
  ├── conftest.py
  ├── unit/                          # Testes unitários de isolamento
  └── e2e/                           # Testes de integração do loop ReAct
```

---

## 5. Matriz de Critérios de Aceite da Versão (DoD Global)

| ID | Cenário | Comportamento Esperado | Como Validar | Status |
|:---|:---|:---|:---|:---|
| CA-01 | Instalação & Setup | Instalação limpa via `pip install -e .` ou `uv pip install -e .` sem erros de dependência | `orion --version` | ⏳ Pendente |
| CA-02 | Core ReAct Loop | Recebe mensagem de usuário, delibera com o modelo e emite tool calls válidas | `pytest tests/unit/test_engine.py` | ⏳ Pendente |
| CA-03 | Blindagem de Governança | Toda tool mutante é interceptada pelo PEP antes de tocar no sistema operacional | `pytest tests/unit/test_pep.py` | ⏳ Pendente |
| CA-04 | RuntimeProvider Isolado | Execução de shell e leitura de arquivos desacoplada de classes internas do Hermes | `pytest tests/unit/test_runtime.py` | ⏳ Pendente |
| CA-05 | Qualidade & Cobertura | 100% dos testes passando com cobertura superior a 85% | `pytest --cov=src/orion` | ⏳ Pendente |

---

## 6. Checklist de Conclusão da Spec (Congelamento)

- [ ] Todas as 4 sprints concluídas e aprovadas.
- [ ] Bateria de testes automatizados com cobertura >= 85%.
- [ ] Atualização de `.claudex/progress.md` e `.claudex/active_context.md`.
- [ ] Tag Git `v0.1.0` criada.
