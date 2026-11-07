# Sprint — v0.5.0 Sprint 3: Contexto, Sessões & Memória

> **Status:** ✅ Implementada  
> **Versão Relacionada:** v0.5.0  
> **Responsável / Agente:** Daniel Dev & Claude  
> **Data de Início:** 2026-11-07  
> **Data de Conclusão:** 2026-11-07  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Sessões longas e baratas: prompt em camadas cacheáveis, auto-compactação, poda de resultados, persistência/resume/rewind e memória realmente ligada ao turno.
* **Dependências Prévias:** Sprint 2.
* **Entregável Verificável:** sessão longa sem estourar contexto, retomável e com recall vetorial funcionando.

---

## 2. Contexto de Engenharia

* **Por que existe:** compactação só manual e por regras; observações intra-turno sem poda; `HybridRetriever`, skills, manifest e `EnvironmentMonitor` existem mas não estão ligados à `AgentSession`; `history` só em RAM.
* **Encaixe:** habilita cache (custo) e continuidade (Jarvis).

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Antes | Depois |
| :--- | :--- | :--- |
| **Compactação** | `/compact` manual | Automática ~80% antes de cada chamada, resumo por LLM barato |
| **Sessão** | RAM | JSONL em `~/.orion/sessions/`, `--continue`, `--resume`, `/rewind` |
| **Memória** | Só `FactsStore` | Recall híbrido, skills, manifest, MEMORY.md |
| **Decisões** | Só ADRs manuais | Tool `record_decision` + recall |

---

## 4. Escopo da Sprint

### ✅ No Escopo
- [x] Prompt em camadas: system → tools → manifest/skills → `CLAUDE.md`/`ORION.md` → histórico, com breakpoints de cache.
- [x] Auto-compactação, poda de `tool_result` antigos, limites de saída por tool, `count_tokens`.
- [x] Ligar `HybridRetriever`, `skills_engine`, `ManifestGenerator`, `EnvironmentMonitor`, `FileSyncer`.
- [x] Sessões persistentes + `/resume`, `/rewind` (conversa e arquivos).
- [x] Decision log (`record_decision`) com fato CONFIRMED e arquivo em `.orion/decisions/`.
- [x] **Tool calling nativo nos providers legados (herdado da Sprint 2):** `OpenRouter` e `Ollama` passam a enviar `tools`/`tool_choice` (formato OpenAI), a montar `tool_use` a partir de `delta.tool_calls` e a converter `tool_use`/`tool_result` do histórico; o failover Anthropic -> OpenRouter -> Ollama preserva tools e histórico estruturado em vez de achatar para texto. Modelos locais sem suporte a tools degradam para texto com aviso explícito.
- [x] Remover `mcp_schema` (redundante desde a Sprint 2: tools MCP já levam o schema completo).

### 🚫 Fora de Escopo
- Daemon e sessão compartilhada entre clientes (Sprint 7).

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/timeline/compactor.py          [mod]
src/orion/gateway/providers/{openrouter,local_ollama}.py [mod]  tool calling nativo
src/orion/gateway/failover.py            [mod]  preservar tools no failover
src/orion/sessions/{store,transcript}.py [novo]
src/orion/memory/{tools,hybrid_retriever}.py [mod]
src/orion/tui/{session.py,commands/*}    [mod]
tests/unit/test_autocompact.py, test_sessions.py, test_decisions.py, test_legacy_tool_calling.py
```

---

## 6. Contratos de Código & Tipagem

```python
class SessionStore(Protocol):
    def append(self, session_id: str, entry: TranscriptEntry) -> None: ...
    def load(self, session_id: str) -> list[TranscriptEntry]: ...
    def list(self, workspace: Path) -> list[SessionMeta]: ...
    def rewind(self, session_id: str, to_entry: int) -> None: ...
```

---

## 7. Estratégia de Implementação

1. Montagem de prompt em camadas e medição de cache hit.
2. Compactação automática e poda.
3. Fiação de memória/skills/manifest.
4. Store de sessões, resume e rewind.
5. Decision log e integração com `/plan` e `/grill-me`.

---

## 8. Testes & Critérios de Aceite (DoD)

- Compactação sob carga preserva tarefa ativa e arquivos relevantes.
- Resume reproduz fielmente; rewind restaura conversa e arquivos.
- Recall vetorial entra no turno dentro do orçamento de 1500 tokens.
- Roteiro com `tool_use` paralelo funciona via OpenRouter e Ollama falsos (servidor HTTP simulado) e atravessa um failover sem perder `tool_result`.
- [x] Sem novos erros de ruff/mypy (o backlog pré-existente permanece); cobertura global 94%; `.claudex/progress.md` atualizado.

---

## 9. Critérios de Parada

1. Perda de dados de sessão em teste de resume/rewind.
2. Compactação que descarte instrução ativa do usuário.

---

## 10. Registro de Implementação

**Desvios e decisões** (as regras vencem o texto original do escopo onde divergem):

- **`count_tokens`:** a contagem exata do provider NÃO é chamada a cada turno (latência de rede por chamada). O gancho estima por 4 caracteres/token e **calibra** a razão contra o `prompt_tokens` real da chamada anterior (`AutoCompactor.observe`, razão limitada a [0,5; 3]).
- **Dois degraus de pressão:** poda de `tool_result` antigos a 60% da janela, compactação a 80% (a poda e a compactação invalidam o cache dali em diante, por isso só sob pressão).
- **Compactação intra-turno:** um único pedido com dezenas de passos de tools é compactado cortando numa mensagem do assistente (pareamento `tool_use`/`tool_result` preservado); o pedido ativo é reinserido literal no resumo. Pós-condição verificada: se o último pedido do usuário não sobreviver, nada é alterado (critério de parada 2).
- **`/compact` manual agora é `async`** (usa o resumidor LLM barato quando online, com fallback determinístico) e só corta entre turnos completos; testes migrados para `await`.
- **Recall por turno** entra como `<recalled_context>` na mensagem do usuário (dado, delimitadores forjados desarmados, não passa pelo filtro de injeção) e não no system, para não quebrar o cache. Orçamento total 1500 tokens (40% fatos, resto episódios). Sem `fastembed`/modelo, degrada para BM25. `ORION_RECALL=0` desliga; a suíte de testes o desliga por padrão (evita download do modelo).
- **`record_decision` é PEP LEVEL_3:** grava fato CONFIRMED (promoção que só o usuário deveria fazer). Arquivo em `<workspace>/.orion/decisions/NNNN-slug.md` (superfície versionável, como `.orion/skills`).
- **Rewind de arquivos** nunca sobrescreve trabalho externo: arquivo alterado fora do ORION desde a mutação é preservado e reportado. Conteúdos ficam em blobs por sessão (`~/.orion/sessions/<ws>/<id>.blobs/`, 0600).
- **Sessões:** JSONL append-only por mensagem (`~/.orion/sessions/<workspace-slug>/<id>.jsonl`); compactação, merge de branch e turno abortado gravam um snapshot `compact`, então `replay` sempre reproduz o histórico vivo. CLI: `--continue/-c`, `--resume/-r <id>`; slash: `/resume`, `/rewind [n] [--conversa]`.
- **Legados:** OpenRouter/Ollama enviam `tools`/`tool_choice`, montam `tool_use` de `delta.tool_calls` (Ollama: `message.tool_calls`) e convertem o histórico; argumentos JSON inválidos viram o sentinela `__invalid_json__` e são recusados pela validação de schema do runtime (o modelo vê o erro). Ollama sem suporte a tools (HTTP 400) degrada a texto com aviso (`LLMResponseChunk.notice`) e o modelo fica marcado no processo. O failover mantém `tools`, `tool_choice` e o histórico estruturado; descarta só `thinking`/`cache_control`.
- **Ollama:** o uso agora é lido dos campos nativos `prompt_eval_count`/`eval_count` (antes lia um `usage` que a API nativa não envia).
- **Remoções:** `MCPSchemaTool`/`mcp_schema` (e seu nível PEP).

**Não validado com provedor real:** nenhum turno pago foi executado (CA-01 segue pendente, ver `baseline.md`). Os testes usam servidor HTTP simulado (aiohttp) para OpenRouter/Ollama e `ScriptedProvider` para a sessão.
