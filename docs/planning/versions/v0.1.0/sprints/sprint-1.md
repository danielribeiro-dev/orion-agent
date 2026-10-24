# Sprint — [v0.1.0] Sprint 1: Tooling, Tipagem & Skeleton

> **Status:** 📋 Planejado  
> **Versão Relacionada:** v0.1.0 (Clean Foundation & Core ReAct Engine)  
> **Responsável / Agente:** Daniel Dev & Antigravity  
> **Data de Início:** A definir (Início da Fase 1)  
> **Data de Conclusão:** —  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Configurar a infraestrutura moderna de tooling do projeto (`pyproject.toml`, gerenciamento de dependências com Pydantic v2, Rich e pytest), o skeleton da pasta `src/orion/` e o comando de terminal base `orion --version` e `orion --help`.
* **Dependências Prévias:** Fase 0 concluída e aprovada.
* **Entregável Verificável:** `pip install -e .` funcional no ambiente virtual, com `orion --version` exibindo o banner ASCII e os testes de infraestrutura passando.

---

## 2. Contexto de Engenharia

* **Por que esta sprint existe:** Para garantir que a nova base de código do ORION nasça com os mais modernos padrões da comunidade Python (PEP 621, tipagem rigorosa, zero dependências circulares e ferramentas de linting/testes configuradas).
* **Como se encaixa na visão global:** Cria a base onde o Core ReAct e o PEP serão implementados nas Sprints 2 e 3.

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Estado Inicial | Estado Final Esperado (DoD) |
| :--- | :--- | :--- |
| **Módulos / Código** | Nenhuma linha de código em `src/` | `pyproject.toml`, `src/orion/__init__.py`, `src/orion/cli.py` criados |
| **CLI** | Comando `orion` não existe no novo repo | `orion --version` e `orion --help` funcionais no terminal |
| **Testes** | 0 testes | Testes de sanidade de CLI e imports passando (`pytest tests/unit/test_cli.py`) |

---

## 4. Escopo da Sprint

### ✅ No Escopo (In Scope)
- [ ] Criação de `pyproject.toml` moderno com metadados do projeto, dependências principais e de desenvolvimento.
- [ ] Criação de `src/orion/__init__.py` com `__version__ = "0.1.0-alpha"`.
- [ ] Criação de `src/orion/cli.py` utilizando `rich` e `click` / `typer` para o ponto de entrada da aplicação.
- [ ] Implementação do renderizador do banner ASCII (Opção C: *The Hunter Crest*) na inicialização da CLI.
- [ ] Configuração do `conftest.py` e testes unitários do ponto de entrada da CLI.

### 🚫 Fora de Escopo (Out of Scope / Anti-Metas)
- Não implementar loop de inferência de LLM (escopo da Sprint 2).
- Não plugar o Hermes ou ferramentas de SO (escopo da Sprint 3).

---

## 5. Arquitetura & Arquivos Afetados

```
orion-agent/
├── pyproject.toml
├── src/
│   └── orion/
│       ├── __init__.py
│       └── cli.py
└── tests/
    ├── conftest.py
    └── unit/
        └── test_cli.py
```

---

## 6. Contratos de Código & Tipagem

```python
# Assinatura formal do entrypoint
from typing import Optional

def main(args: Optional[list[str]] = None) -> int:
    """Ponto de entrada oficial da CLI do ORION.
    
    Retorna 0 em caso de sucesso, ou código de erro diferente de 0.
    """
    ...
```

---

## 7. Definition of Done (DoD)

- [ ] `pyproject.toml` configurado e validado.
- [ ] `pip install -e .` instala o pacote sem warnings de configuração.
- [ ] `orion --version` exibe a versão correta e o banner ASCII.
- [ ] `pytest tests/unit/test_cli.py` passa com 100% de sucesso.
- [ ] `.claudex/progress.md` atualizado com o encerramento da Sprint 1.
