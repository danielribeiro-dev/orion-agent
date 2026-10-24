# ORION-Agent — Gateway de Modelos & Livro-Razão de Custos (Cost Ledger)

> Especificação da camada de abstração de LLMs, roteamento inteligente e observabilidade de consumo financeiro e tokens em tempo real.

---

## 1. Consciência Operacional de Custos

Diferente de assistentes convencionais que chamam modelos caros indiscriminadamente, o ORION possui **visão financeira explícita de sua própria operação**:

- Cada requisição calcula e registra tokens de entrada, tokens de saída e o valor estimado em dólares (USD) e reais (BRL).
- Usuários podem definir limites diários ou mensais de orçamento (ex: `$5.00/dia`). Ao se aproximar de 85% do teto, o ORION avisa o usuário e oferece estratégias de economia.

---

## 2. A Matriz de Roteamento Inteligente

O ORION classifica tarefas dinamicamente para escolher o modelo mais eficiente em custo-benefício:

```
Complexidade da Tarefa
        │
        ├─▶ [Baixa Complexidade] ───▶ Modelos Rápidos e Econômicos
        │   (Triagem, resumos, tone)    Ex: Gemini 2.5 Flash Lite / Claude 3.5 Haiku
        │
        ├─▶ [Média Complexidade] ───▶ Modelos de Execução Geral
        │   (Edição simples, bash, TUI)  Ex: GPT-4o-mini / DeepSeek V3 / Qwen 2.5
        │
        ├─▶ [Alta Complexidade] ────▶ Modelos de Raciocínio Profundo
        │   (Arquitetura, bugs sutis)   Ex: Claude 3.7 Sonnet / Gemini 2.0 Pro / GPT-4o
        │
        └─▶ [Sensível / Modo Offline]▶ Modelos Locais (100% Gratuito e Privado)
            (Sem internet, dados locais) Ex: Ollama (Llama 3 / Qwen Coder)
```

---

## 3. Provedores Suportados

A integração do gateway é desacoplada e aceita:
1. **OpenRouter:** Acesso unificado a centenas de modelos com monitoramento de saldo em tempo real.
2. **Google Gemini API:** Integração direta com quotas generosas e modelos rápidos de alta capacidade.
3. **Anthropic API:** Modelos Claude de excelência para codificação e planejamento.
4. **OpenAI API:** GPT-4o e modelos da família o-series.
5. **Local / OpenAI-Compatible:** Ollama, vLLM, LM Studio ou qualquer endpoint compatível com o padrão OpenAI.

---

## 4. O Livro-Razão de Custos (`cost_ledger`)

Todos os consumos são persistidos localmente no banco `~/.orion/metrics.db`:

```sql
CREATE TABLE token_ledger (
    id TEXT PRIMARY KEY,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    estimated_cost_usd REAL NOT NULL,
    task_id TEXT,
    branch_name TEXT,
    success BOOLEAN NOT NULL
);
```

O comando `/cost` no terminal gera um relatório visual instantâneo com gráfico de gastos por tarefa, modelo e período.
