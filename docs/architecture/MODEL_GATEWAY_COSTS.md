# O.R.I.O.N — Gateway de Modelos, Roteamento Dinâmico & Livro-Razão de Custos
*(Operational Reasoning & Intelligence Orchestration Network)*

> Especificação da camada de abstração de LLMs, inteligência de seleção de modelos por complexidade, observabilidade de tokens no CLI e governança financeira em tempo real.

---

## 1. Consciência Operacional de Custos e Tokens no CLI

Inspirado no padrão de observabilidade de ferramentas como **Claude Code**, o O.R.I.O.N possui transparência total sobre seu próprio consumo computacional:

- **Feedback Visual Instantâneo:** Ao final de cada turno ou comando, o CLI exibe de forma discreta na status bar ou no rodapé a métrica exata de consumo:
  ```text
  [ORION] Turno concluído em 1.4s | Tokens: 842 in / 128 out | Custo: $0.0014 (R$ 0,0078) | Modelo: claude-3-7-sonnet
  ```
- **Limites de Orçamento (Budgeting):** O usuário pode estipular limites de gastos (ex: `$5.00/dia`). Ao atingir 85% do teto, o sistema emite alerta e sugere alternar para modelos mais econômicos ou 100% locais (Ollama).

---

## 2. Modos de Roteamento de Modelos: Automático vs. Fixo

O usuário tem controle total sobre como os modelos de inteligência são selecionados, com configuração via comando `/config` ou **linguagem natural direta no chat**:

```
Modos de Seleção de Modelo
         │
         ├──▶ [Modo Automático (Dynamic Auto-Routing) — Padrão Recomendado]
         │    O ORION avalia autonomamente a complexidade de cada passo:
         │    • Tarefa pesada em raciocínio/arquitetura ──▶ Chaveia para modelo de topo (ex: Claude 3.7 Sonnet / Opus / Gemini 2.0 Pro)
         │    • Tarefas de execução, leitura e scripts  ──▶ Retorna automaticamente para modelos rápidos/econômicos (ex: Gemini 2.5 Flash / Qwen 2.5 Coder)
         │
         └──▶ [Modo Fixo (Fixed Model)]
              O usuário fixa um modelo específico (ex: "orion config model gemini-2.5-flash" ou "Orion, use apenas claude-3-7-sonnet")
              Todas as etapas respeitam estritamente a escolha do usuário.
```

### Configuração por Linguagem Natural ou CLI:
- *"Orion, mude para o modo automático de modelos"* ──▶ Ativa o Dynamic Auto-Routing.
- *"Orion, fixe no Claude 3.7 Sonnet para a sessão de hoje"* ──▶ Crava o modelo fixo.
- `/config model --mode auto` ou `/config model --set openrouter/anthropic/claude-3.7-sonnet`.

---

## 3. Integração com Provedores & OpenRouter

O Gateway opera com uma camada limpa e agnóstica de provedores:

1. **OpenRouter (Seleção Ampla):** Com a chave de API do OpenRouter configurada pelo usuário, o ORION possui acesso a milhares de modelos do ecossistema global, selecionando dinamicamente a melhor alternativa de custo-benefício em modo automático.
2. **Google Gemini API:** Acesso direto a modelos de latência ultrabaixa e janelas de contexto massivas (Gemini 2.5 Flash, Gemini 2.0 Pro).
3. **Anthropic API:** Modelos Claude para engenharia de software de alta precisão e extended thinking.
4. **OpenAI API:** GPT-4o e modelos da família de raciocínio.
5. **Local / OpenAI-Compatible (Ollama, vLLM, LM Studio):** Execução 100% offline, gratuita e privativa para momentos sem conexão ou dados ultrassensíveis (*ORION Imortal*).

---

## 4. O Livro-Razão de Custos (`cost_ledger`)

Todos os consumos são persistidos no banco local SQLite `~/.orion/metrics.db`:

```sql
CREATE TABLE token_ledger (
    id TEXT PRIMARY KEY,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    routing_mode TEXT NOT NULL,          -- 'auto' ou 'fixed'
    complexity_level TEXT NOT NULL,      -- 'LOW', 'MEDIUM', 'HIGH'
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    estimated_cost_usd REAL NOT NULL,
    estimated_cost_brl REAL NOT NULL,
    task_id TEXT,
    branch_name TEXT,
    success BOOLEAN NOT NULL
);
```

O comando `/cost` no terminal gera um relatório visual em Rich com gráficos tabulares de consumo por tarefa, modelo, dia e mês.
