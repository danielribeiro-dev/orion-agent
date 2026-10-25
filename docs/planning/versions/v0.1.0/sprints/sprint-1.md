# Sprint — [v0.1.0] Sprint 1: Tooling, Tipagem & Skeleton

> **Status:** ✅ Concluída  
> **Versão Relacionada:** v0.1.0 (Clean Foundation & Core ReAct Engine)  
> **Responsável / Agente:** Daniel Dev & Antigravity  
> **Data de Início:** 2026-10-24  
> **Data de Conclusão:** 2026-10-24  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Configurar a infraestrutura moderna de desenvolvimento (`pyproject.toml`, Pydantic v2, Rich, Typer/Click, pytest), o skeleton limpo da pasta `src/orion/`, o comando base `orion --version` e `orion --help` exibindo o banner ASCII *The Hunter Crest*, e os contratos tipados de configuração (`src/orion/config.py`), preparando o suporte a modos de operação (`auto` vs `fixed`) e seleção de provedores (OpenRouter, Gemini, Anthropic, OpenAI, Ollama).
* **Dependências Prévias:** Fase 0 formalmente concluída e aprovada.
* **Entregável Verificável:** `pip install -e .` ou `uv pip install -e .` funcional no ambiente virtual, com `orion --version` rodando em < 100ms exibindo o banner ASCII e os testes de infraestrutura e contratos passando.

---

## 2. Contexto de Engenharia

* **Por que esta sprint existe:** Para garantir que a nova base de código do O.R.I.O.N nasça sob os mais rigorosos padrões da comunidade Python moderna (PEP 621, tipagem Pydantic v2 rigorosa, zero acoplamento legado e tooling de linting/testes automatizados).
* **Como se encaixa na visão global:** Cria a casca robusta e tipada onde o motor ReAct (Sprint 2) e as 5 ferramentas primitivas com PEP (Sprint 3) serão conectados.

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Estado Inicial | Estado Final Esperado (DoD) |
| :--- | :--- | :--- |
| **Módulos / Código** | 0 arquivos em `src/` | `pyproject.toml`, `src/orion/__init__.py`, `src/orion/cli.py`, `src/orion/config.py` criados |
| **CLI & Banner** | Comando `orion` não existe | `orion --version` e `orion --help` funcionais com banner ASCII *The Hunter Crest* |
| **Tipagem & Modelos** | Inexistente | Modelos Pydantic v2 tipados para configuração de agentes e provedores |
| **Testes** | 0 testes | Testes de sanidade de CLI e configuração passando (`pytest tests/unit/test_cli.py`, `test_config.py`) |

---

## 4. Escopo da Sprint

### ✅ No Escopo (In Scope)
- [x] Configuração de `pyproject.toml` moderno com metadados do projeto, dependências principais (`pydantic>=2.0`, `rich`, `typer`, `httpx`) e de desenvolvimento (`pytest`, `pytest-cov`, `pytest-asyncio`, `ruff`, `mypy`).
- [x] Criação de `src/orion/__init__.py` com `__version__ = "0.1.0-alpha"`.
- [x] Implementação de `src/orion/cli.py` utilizando `rich` e `typer` para o ponto de entrada da aplicação, renderizando o banner ASCII oficial *The Hunter Crest*.
- [x] Implementação de `src/orion/config.py` com dataclasses/modelos Pydantic v2 representando:
  - `RoutingMode`: Enum (`AUTO`, `FIXED`).
  - `ProviderConfig`: Suporte a OpenRouter, Gemini, Anthropic, OpenAI, Ollama.
  - `OrionConfig`: Configuração geral de paths (`~/.orion/` global e `.orion/` local), teto de orçamento e modo de autonomia.
- [x] Configuração do `tests/conftest.py` e testes unitários de inicialização de CLI e parsing de configurações.

### 🚫 Fora de Escopo (Out of Scope / Anti-Metas)
- Não implementar loop de inferência de LLM ou chamadas de API (escopo da Sprint 2).
- Não plugar ferramentas de SO ou PEP nesta sprint (escopo da Sprint 3).

---

## 5. Arquitetura & Arquivos Afetados

```
orion-agent/
├── pyproject.toml
├── src/
│   └── orion/
│       ├── __init__.py
│       ├── cli.py
│       └── config.py
└── tests/
    ├── conftest.py
    └── unit/
        ├── test_cli.py
        └── test_config.py
```

---

## 6. Definition of Done (DoD)

- [x] `pyproject.toml` configurado e validado via `pip install -e .` no ambiente virtual `.venv`.
- [x] `orion --version` exibe a versão correta e o banner *The Hunter Crest* estilizado em Rich.
- [x] `orion --help` documenta os subcomandos e opções fundamentais.
- [x] Modelos de configuração em `src/orion/config.py` passam em testes de validação Pydantic.
- [x] `pytest tests/unit/test_cli.py tests/unit/test_config.py` passa com 100% de sucesso (41 testes).
- [x] Cobertura de testes atingida: **97.48%** (meta: $\ge 85\%$).
- [x] `.claudex/progress.md` atualizado com o encerramento da Sprint 1.
