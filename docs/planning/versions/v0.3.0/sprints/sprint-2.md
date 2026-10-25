# Sprint — [v0.3.0] Sprint 2: Dynamic Auto-Routing & Complexity Engine

> **Status:** 📋 Planejado  
> **Versão Relacionada:** v0.3.0 (Model Gateway, Real-Time Cost Ledger & Offline Resilience)  
> **Responsável / Agente:** Daniel Dev & Antigravity  
> **Data de Início:** A definir (Fase 3)  
> **Data de Conclusão:** —  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Desenvolver o motor de **Dynamic Auto-Routing** intra-agente, capaz de avaliar a complexidade cognitiva de cada turno ou tarefa e selecionar de forma autônoma o modelo ideal em três tiers (*Fast/Lite*, *Balanced*, *Heavy Frontier*), suportando também o modo de modelo fixo (`fixed`) definido pelo usuário.
* **Dependências Prévias:** Sprint 1 da v0.3.0 concluída (`ModelRegistry` e `OpenRouterProvider`).
* **Entregável Verificável:** Módulo `src/orion/gateway/router.py` operacional, integrando ao ReAct Engine da v0.1.0 e direcionando tarefas de leitura/grep para modelos rápidos e tarefas de arquitetura/código denso para modelos com raciocínio estendido.

---

## 2. Contexto de Engenharia

* **Por que esta sprint existe:** Em um fluxo de trabalho real de desenvolvimento, cerca de 60% das chamadas a modelos são tarefas operacionais simples (ler arquivos, filtrar logs de erro, inspecionar diffs). Chamar um modelo caríssimo de topo em todas as voltas gera custos excessivos e latência desnecessária. O Auto-Routing inspirado no RouteLLM garante máxima inteligência com economia agressiva.
* **Como se encaixa na visão global:** Implementa a inteligência de roteamento descrita em `docs/architecture/MODEL_GATEWAY_COSTS.md`.
* **Decisões arquiteturais associadas:** ADR-009 (Dynamic Auto-Routing por Complexidade).

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Estado Inicial (Antes da Sprint) | Estado Final Esperado (DoD) |
| :--- | :--- | :--- |
| **Seleção de Modelo** | Estática ou por mock único | Dinâmica baseada em heurísticas e perfil de tarefa |
| **Modos de Operação** | Não suportados | Modos `auto` e `fixed` configuráveis por comando ou prompt |
| **Níveis de Complexidade** | Inexistentes | Tiers `FAST_LITE`, `BALANCED` e `HEAVY_FRONTIER` |
| **Latência Média** | Idêntica para qualquer tarefa | Redução de até 60% da latência em turnos de inspeção |

---

## 4. Escopo da Sprint

### ✅ No Escopo (In Scope)
- [ ] Implementação de `ComplexityClassifier` em `src/orion/gateway/classifier.py`:
  - Análise léxica e contextual do prompt do usuário e histórico do turno.
  - Indicadores de alta complexidade: comandos `/plan`, refatoração multifuncional, raciocínio de segurança, depuração de erros complexos, planejamento arquitetural.
  - Indicadores de baixa complexidade: leitura de diretórios, formatação de dados, checagem de status, sumarização simples.
- [ ] Implementação do `ModelRouter` em `src/orion/gateway/router.py`:
  - Mapeamento dinâmico de tiers:
    - `FAST_LITE`: ex. Google Gemini 2.5 Flash / Qwen 2.5 Coder 32B via OpenRouter.
    - `BALANCED`: ex. Claude 3.5 Sonnet / GPT-4o-mini.
    - `HEAVY_FRONTIER`: ex. Claude 3.7 Sonnet (com extended thinking habilitado) / Gemini 2.0 Pro.
  - Suporte ao modo `fixed`: bypass do classificador e uso estrito do modelo escolhido pelo usuário.
- [ ] Suporte à alternância dinâmica por linguagem natural (*"Orion, alterne para o modo automático"* ou *"Orion, fixe no Claude 3.7 Sonnet"*).
- [ ] Testes unitários com benchmarks de roteamento em `tests/unit/test_router.py`.

### 🚫 Fora de Escopo (Out of Scope / Anti-Metas)
- Não persistir o histórico financeiro no banco SQLite (escopo da Sprint 3).
- Não gerenciar falhas de conexão de rede ou failover para Ollama (escopo da Sprint 4).

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/gateway/
├── classifier.py                      # Avaliador heurístico de complexidade do turno
└── router.py                          # Roteador com suporte a modos auto e fixed
tests/unit/
└── test_router.py                     # Cenários de teste de classificação e seleção de modelo
```

---

## 6. Contratos de Código & Tipagem

```python
from enum import Enum
from typing import Optional
from pydantic import BaseModel

class ComplexityLevel(str, Enum):
    FAST_LITE = "fast_lite"
    BALANCED = "balanced"
    HEAVY_FRONTIER = "heavy_frontier"

class RoutingMode(str, Enum):
    AUTO = "auto"
    FIXED = "fixed"

class RoutingDecision(BaseModel):
    selected_model: str
    complexity: ComplexityLevel
    mode: RoutingMode
    reason: str
```

---

## 7. Critérios de Aceite (DoD)

- [ ] Prompts contendo palavras-chave de arquitetura ou `/plan` classificam como `HEAVY_FRONTIER`.
- [ ] Tarefas simples de inspeção de arquivos classificam como `FAST_LITE`.
- [ ] No modo `fixed`, a escolha do usuário é respeitada 100% das vezes independentemente da complexidade.
- [ ] Suíte de testes unitários passando com cobertura $\ge 85\%$.
