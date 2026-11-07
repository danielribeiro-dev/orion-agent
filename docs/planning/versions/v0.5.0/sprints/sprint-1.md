# Sprint — v0.5.0 Sprint 1: Provider Anthropic Nativo

> **Status:** ✅ Implementada (teste live pendente de chave)  
> **Versão Relacionada:** v0.5.0  
> **Responsável / Agente:** Daniel Dev & Claude  
> **Data de Início:** 2026-11-06  
> **Data de Conclusão:** 2026-11-06  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Falar com Claude pela Messages API nativa, com modelo de mensagens estruturado, prompt caching, thinking, retry em streaming e failover.
* **Dependências Prévias:** Sprint 0.
* **Entregável Verificável:** turno real (opt-in `ORION_LIVE=1`) com streaming, uso e cache contabilizados no `CostLedger`.

---

## 2. Contexto de Engenharia

* **Por que existe:** `LLMMessage.content` é `str`, `LLMRequest` não tem `tools`/`system`/`cache_control`; todo Claude passa por OpenRouter em formato OpenAI; `stream()` não tem retry.
* **Encaixe:** base de todas as sprints seguintes (ADR-020, ADR-021).

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Antes | Depois |
| :--- | :--- | :--- |
| **Módulos** | Só OpenRouter e Ollama | + `gateway/providers/anthropic.py` |
| **Modelo** | `content: str` | `ContentBlock` (text, thinking, tool_use, tool_result, image) |
| **Resiliência** | Retry só em `complete()` | Retry/reconexão também em `stream()`; breaker ligado |
| **Custo** | Cache lido, não precificado | Cache read/write precificado |

---

## 4. Escopo da Sprint

### ✅ No Escopo
- [x] `ContentBlock`, `LLMRequest.system/tools/tool_choice/thinking`, `cache_control`.
- [x] `AnthropicProvider` (streaming tipado, thinking, `count_tokens`, usage com cache).
- [x] Retry com backoff em `stream()` (extraído para `providers/base.py`, reutilizado por todos).
- [x] Registry com Claude 5 (`claude-fable-5-1`, `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`) e tiers.
- [x] Failover Anthropic → OpenRouter → Ollama via `CircuitBreaker` ligado à sessão, sem downgrade silencioso de modelo de código.
- [x] `ANTHROPIC_API_KEY` (ou arquivo em `~/.orion/`), validação no `orion doctor`.
- [x] Adaptador de compatibilidade para os providers antigos (strings → blocos).

### 🚫 Fora de Escopo
- Loop de `tool_use` (Sprint 2), auto-compactação (Sprint 3).

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/gateway/{models,registry,router}.py        [mod]
src/orion/gateway/providers/{base,anthropic}.py      [mod/novo]
src/orion/gateway/{ledger,circuit_breaker}.py        [mod]
src/orion/config.py, cli.py (doctor)                 [mod]
tests/unit/test_anthropic_provider.py, test_failover.py
```

---

## 6. Contratos de Código & Tipagem

```python
class ContentBlock(BaseModel):
    type: Literal["text", "thinking", "tool_use", "tool_result", "image"]
    # campos por tipo; tool_use: id, name, input; tool_result: tool_use_id, content, is_error

class LLMMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str | list[ContentBlock]

class LLMRequest(BaseModel):
    system: str | list[ContentBlock] | None = None
    tools: list[ToolSpec] = []
    tool_choice: ToolChoice | None = None
    thinking: ThinkingConfig | None = None
```

---

## 7. Estratégia de Implementação

1. Estender modelos com compatibilidade retroativa e adaptador.
2. Implementar `AnthropicProvider` contra servidor SSE falso no formato real.
3. Extrair retry para a base e aplicar a `stream()`.
4. Registry, tiers, custo de cache.
5. Ligar breaker/failover na `AgentSession`.
6. Teste live opt-in.

---

## 8. Testes & Critérios de Aceite (DoD)

- SSE falso: text, thinking, tool_use, erro no meio do stream, 429/5xx com retry.
- Contabilidade de cache read/write no ledger.
- Failover não troca silenciosamente para modelo inferior em tarefa de código.
- [ ] Suíte anterior verde; mypy/ruff limpos; cobertura ≥ 85%; `.claudex/progress.md` atualizado.

---

## 9. Critérios de Parada

1. Quebra de contrato público do Gateway que não caiba no adaptador.
2. Mudança de formato da API Anthropic que invalide o desenho (revisar com o Senhor).
