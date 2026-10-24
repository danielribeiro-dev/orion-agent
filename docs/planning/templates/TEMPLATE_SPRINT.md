# Sprint — [vX.Y.Z] Sprint [N]: [Nome da Sprint]

> **Status:** 📋 Planejando | 🔄 Em Execução | ✅ Concluída  
> **Versão Relacionada:** [vX.Y.Z]  
> **Responsável / Agente:** [Nome / Par de Desenvolvimento]  
> **Data de Início:** [YYYY-MM-DD]  
> **Data de Conclusão:** [YYYY-MM-DD ou —]  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** [1–2 frases diretas explicando exatamente o que esta sprint constrói e valida].
* **Dependências Prévias:** [Sprints anteriores ou componentes necessários prontos].
* **Entregável Verificável:** [O que estará funcionando e testável ao final desta sprint].

---

## 2. Contexto de Engenharia

* **Por que esta sprint existe:** [Explicação do problema técnico ou necessidade de arquitetura].
* **Como se encaixa na visão global:** [Relação com o Roadmap geral e com os contratos imutáveis].
* **Decisões arquiteturais associadas:** [Referência a ADRs em `.claudex/decisions.md`].

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Estado Inicial (Antes da Sprint) | Estado Final Esperado (DoD) |
| :--- | :--- | :--- |
| **Módulos / Código** | [Ex: Não existe o módulo X] | [Ex: Módulo X implementado e tipado] |
| **Comportamento** | [Ex: Falha se chamar a tool Y] | [Ex: Retorna `RuntimeResult` válido] |
| **Testes** | [Ex: 0 testes para o componente] | [Ex: Suíte unitária passando com 90%+ cobertura] |

---

## 4. Escopo da Sprint

### ✅ No Escopo (In Scope)
- [ ] [Item de escopo 1]
- [ ] [Item de escopo 2]
- [ ] [Item de escopo 3]

### 🚫 Fora de Escopo (Out of Scope / Anti-Metas)
- [O que NÃO será feito nesta sprint para evitar scope creep]
- [Features que pertencem a sprints posteriores]

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/
  ├── [novo ou modificado] caminho/para/arquivo.py
tests/
  └── unit/test_componente.py
```

---

## 6. Contratos de Código & Tipagem

```python
# Assinaturas formais e contratos que DEVEM ser respeitados
from dataclasses import dataclass
from typing import Any, Optional

@dataclass
class ExemploContrato:
    id: str
    status: str
    data: Optional[Any] = None
```

---

## 7. Estratégia de Implementação (Passo a Passo)

1. **Passo 1:** [Descrição do primeiro passo técnico].
2. **Passo 2:** [Segundo passo de implementação].
3. **Passo 3:** [Criação dos testes unitários correspondentes].
4. **Passo 4:** [Execução dos testes e verificação de regressões].

---

## 8. Testes Automatizados & Critérios de Aceite (DoD)

### Cenários de Teste Obrigatórios
- **Teste 1:** [Entrada X produz Saída Y].
- **Teste 2:** [Comportamento gracioso em caso de erro Z].
- **Teste 3:** [Validação de invariante de segurança].

### Definition of Done (DoD)
- [ ] Todos os itens do escopo implementados.
- [ ] Tipagem Pydantic / Mypy sem erros.
- [ ] Testes unitários passando (`pytest tests/unit/...`).
- [ ] Nenhuma regressão nos testes existentes.
- [ ] Documentação de progresso atualizada em `.claudex/progress.md`.

---

## 9. Critérios de Parada (Stop Conditions)

A execução desta sprint deve ser pausada para revisão humana se:
1. Um contrato público de versão anterior precisar ser quebrado.
2. Houver falha de segurança ou inconsistência não prevista na especificação.
