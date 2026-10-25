# Sprint — [v0.3.0] Sprint 3: Real-Time Multi-Currency Cost Ledger & Budgeting

> **Status:** 📋 Planejado  
> **Versão Relacionada:** v0.3.0 (Model Gateway, Real-Time Cost Ledger & Offline Resilience)  
> **Responsável / Agente:** Daniel Dev & Antigravity  
> **Data de Início:** A definir (Fase 3)  
> **Data de Conclusão:** —  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Construir o livro-razão financeiro local de consumo computacional (`CostLedger`) baseado em SQLite WAL em `~/.orion/metrics.db`, calculando custos exatos por milhão de tokens em USD e convertendo para BRL com base em taxa cambial configurável/atualizável, além de gerenciar limites rígidos de orçamento diário (*Daily Budget Cap*).
* **Dependências Prévias:** Sprint 1 e Sprint 2 da v0.3.0 concluídas.
* **Entregável Verificável:** Módulo `src/orion/gateway/ledger.py` e `src/orion/gateway/budget.py` funcionais, gravando métricas a cada turno concluído, alertando o usuário ao atingir 85% do teto diário e travando chamadas pagas ao atingir 100%.

---

## 2. Contexto de Engenharia

* **Por que esta sprint existe:** Para dar ao usuário visibilidade e controle total sobre seus custos de IA. Nenhum desenvolvedor quer ser surpreendido por faturas inesperadas ao final do mês decorrentes de loops de agentes. A transparência de tokens em tempo real é uma das marcas de maturidade de produtos como o Claude Code.
* **Como se encaixa na visão global:** Alimenta os dados exibidos na barra de status inferior do Stream CLI da v0.4.0 e os relatórios do comando `/cost`.
* **Decisões arquiteturais associadas:** ADR-009 (Ledger de Custos no CLI e métricas persistidas em SQLite).

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Estado Inicial (Antes da Sprint) | Estado Final Esperado (DoD) |
| :--- | :--- | :--- |
| **Persistência de Custos** | Nenhuma | Banco local SQLite WAL `~/.orion/metrics.db` |
| **Moeda de Exibição** | Apenas contagem bruta de tokens | USD e BRL calculados em tempo real por turno |
| **Governança de Gastos** | Inexistente | Limite orçamentário configurável (ex: $2.00/dia) com alertas proativos |
| **Rastreamento de Cache** | Inexistente | Distinção de custo entre tokens normais e tokens cacheados |

---

## 4. Escopo da Sprint

### ✅ No Escopo (In Scope)
- [ ] Schema SQLite WAL em `src/orion/gateway/ledger.py`:
  - Criação automática da tabela `token_ledger` com índices de performance em `timestamp` e `model`.
  - Método `record_turn_cost(turn_id, provider, model, tokens_in, tokens_out, tokens_cached, routing_mode, complexity)`.
- [ ] Módulo de Orçamento em `src/orion/gateway/budget.py`:
  - Configuração de teto de gastos diário (`daily_budget_usd`).
  - Verificação prévia antes de cada despacho de inferência.
  - Alerta ao atingir 85% do orçamento.
  - Bloqueio ou sugestão de chaveamento para modelos locais ao atingir 100%.
- [ ] Mecanismo de conversão cambial USD $\rightarrow$ BRL (valor default configurável em `~/.orion/config.json`).
- [ ] Suíte de testes unitários em `tests/unit/test_ledger.py` e `tests/unit/test_budget.py`.

### 🚫 Fora de Escopo (Out of Scope / Anti-Metas)
- Não renderizar tabelas visuais ricas em ASCII/Rich no terminal (escopo do comando `/cost` na v0.4.0).
- Não gerenciar chaveamento de falha de conexão offline (escopo da Sprint 4).

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/gateway/
├── ledger.py                          # Banco SQLite WAL de métricas e custos (~/.orion/metrics.db)
└── budget.py                          # Lógica de controle de limites orçamentários (diário/mensal)
tests/unit/
├── test_ledger.py                     # Testes de gravação, agregação e cálculo de custos
└── test_budget.py                     # Testes de detecção de teto e emissão de alertas
```

---

## 6. Contratos de Código & Tipagem

```python
from datetime import datetime
from pydantic import BaseModel

class CostRecord(BaseModel):
    id: str
    timestamp: datetime
    provider: str
    model: str
    routing_mode: str
    complexity_level: str
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    cost_usd: float
    cost_brl: float
    task_id: str | None = None

class BudgetStatus(BaseModel):
    daily_budget_usd: float
    spent_today_usd: float
    percentage_used: float
    limit_reached: bool
    warning_triggered: bool
```

---

## 7. Critérios de Aceite (DoD)

- [ ] Toda chamada de modelo grava uma linha atômica em `token_ledger`.
- [ ] O cálculo de custo considera o desconto de tokens em cache conforme a tabela de preços do `ModelRegistry`.
- [ ] Ao atingir o limite orçamentário configurado, novas requisições a APIs pagas são bloqueadas e emitem erro tipado `BudgetExceededError`.
- [ ] Testes unitários com cobertura $\ge 85\%$.
