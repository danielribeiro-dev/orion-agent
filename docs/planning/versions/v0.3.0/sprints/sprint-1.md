# Sprint — [v0.3.0] Sprint 1: Model Registry & OpenRouter Provider

> **Status:** 📋 Planejado  
> **Versão Relacionada:** v0.3.0 (Model Gateway, Real-Time Cost Ledger & Offline Resilience)  
> **Responsável / Agente:** Daniel Dev & Antigravity  
> **Data de Início:** A definir (Fase 3)  
> **Data de Conclusão:** —  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Criar o contrato abstrato de provedores de inferência (`BaseLLMProvider`), o catálogo tipado de modelos (`ModelRegistry`) com suporte a múltiplos provedores e a implementação de primeira classe do conector do **OpenRouter** com suporte a streaming de tokens assíncrono e extração de métricas de uso (tokens de entrada, saída, raciocínio e cache).
* **Dependências Prévias:** v0.2.0 concluída (Memória Tríplice e sistema de skills disponíveis).
* **Entregável Verificável:** Módulo `src/orion/gateway/providers/openrouter.py` operacional, executando chamadas de streaming e retornando respostas estruturadas com medição precisa de tokens contra endpoints mockados e reais.

---

## 2. Contexto de Engenharia

* **Por que esta sprint existe:** Para desatrelar o ORION de qualquer modelo ou API específica. Enquanto Claude Code só funciona com Anthropic e Antigravity foca no ecossistema Gemini, o ORION nasce com o OpenRouter como hub unificado de centenas de modelos abertos e proprietários sob uma única chave.
* **Como se encaixa na visão global:** Serve de alicerce para o roteamento dinâmico (Sprint 2) e o livro-razão de custos (Sprint 3).
* **Decisões arquiteturais associadas:** ADR-002 (Núcleo Aberto com integrações agnósticas), ADR-019 (OpenRouter como provedor prioritário).

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Estado Inicial (Antes da Sprint) | Estado Final Esperado (DoD) |
| :--- | :--- | :--- |
| **Camada de Modelos** | Mocks de teste no ReAct Engine | Gateway desacoplado com provedores plugáveis |
| **Provedor Primário** | Inexistente | `OpenRouterProvider` com suporte a streaming e contagem de tokens |
| **Model Registry** | Nenhum | Catálogo tipado com custos por milhão de tokens (USD) e limites de contexto |
| **Streaming** | Não implementado | Async generator emitindo deltas de texto e chunks de raciocínio |

---

## 4. Escopo da Sprint

### ✅ No Escopo (In Scope)
- [ ] Modelos Pydantic v2 em `src/orion/gateway/models.py`:
  - `LLMMessage` (`role`, `content`, `reasoning_content`)
  - `LLMRequest` (`model`, `messages`, `temperature`, `max_tokens`, `stream`)
  - `LLMResponseChunk` (`delta`, `is_final`, `usage`)
  - `LLMResponse` (`content`, `model`, `usage`, `latency_ms`)
  - `ModelSpec` (`id`, `name`, `provider`, `context_window`, `cost_input_m`, `cost_output_m`, `supports_thinking`)
- [ ] Classe abstrata `BaseLLMProvider` em `src/orion/gateway/providers/base.py`:
  - `async def complete(request: LLMRequest) -> LLMResponse`
  - `async def stream(request: LLMRequest) -> AsyncIterator[LLMResponseChunk]`
- [ ] Implementação de `OpenRouterProvider` em `src/orion/gateway/providers/openrouter.py`:
  - Conexão HTTP/2 assíncrona (`httpx`) com backoff exponencial.
  - Streaming SSE nativo.
  - Extração de cabeçalhos de custos e payload de usage (`prompt_tokens`, `completion_tokens`).
- [ ] Suíte de testes com mocks assíncronos em `tests/unit/test_openrouter.py`.

### 🚫 Fora de Escopo (Out of Scope / Anti-Metas)
- Não implementar lógica de classificação de complexidade de prompts (escopo da Sprint 2).
- Não gravar em banco SQLite de custos (escopo da Sprint 3).
- Não plugar o Ollama local (escopo da Sprint 4).

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/gateway/
├── __init__.py
├── models.py                          # Modelos Pydantic de requisição, resposta e especificações de modelo
├── registry.py                        # Catálogo de modelos suportados e metadados de preço
└── providers/
    ├── __init__.py
    ├── base.py                        # Interface BaseLLMProvider
    └── openrouter.py                  # Cliente assíncrono OpenRouter (httpx + SSE)
tests/unit/
└── test_openrouter.py                 # Testes unitários com fixtures e mocks
```

---

## 6. Contratos de Código & Tipagem

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional
from pydantic import BaseModel, Field

class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    total_tokens: int = 0

class LLMResponseChunk(BaseModel):
    delta: str = ""
    reasoning_delta: Optional[str] = None
    is_final: bool = False
    usage: Optional[TokenUsage] = None

class BaseLLMProvider(ABC):
    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Execução síncrona/completa de inferência."""
        pass

    @abstractmethod
    def stream(self, request: LLMRequest) -> AsyncIterator[LLMResponseChunk]:
        """Streaming assíncrono token a token."""
        pass
```

---

## 7. Critérios de Aceite (DoD)

- [ ] Todas as chamadas para `OpenRouterProvider` retornam streams e contagens válidas de tokens.
- [ ] Erros de autenticação, rate-limit (429) e timeout tratam exceções tipadas de domínio (`ProviderAPIError`, `RateLimitError`).
- [ ] Testes unitários com cobertura $\ge 85\%$ sem chamadas de rede externas em testes automatizados.
