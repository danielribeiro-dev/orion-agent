# ORION-Agent — Model Context Protocol (MCP) & Extensibilidade de Canais

> Especificação de extensibilidade aberta: cliente nativo MCP, integração com canais (Telegram, WhatsApp, etc.) e rotas HTTP padronizadas.

---

## 1. O Padrão Model Context Protocol (MCP)

Para garantir que o ORION seja um sistema **100% aberto e extensível**, adotamos o **MCP** como o protocolo de primeira classe para ferramentas externas:

- Em vez de escrever integrações proprietárias para cada banco de dados, navegador ou ferramenta, o ORION conecta-se diretamente a qualquer **Servidor MCP** padrão da comunidade.
- **Suporte a Transportes:**
  - `stdio`: Spawna processos locais (Node/Python) para rodar ferramentas no computador do usuário.
  - `SSE` (Server-Sent Events): Conexão com servidores MCP remotos via HTTP/WebSocket.
- **Lazy Loading de Ferramentas:**
  - As ferramentas MCP são descobertas dinamicamente e seus schemas JSON só são injetados no contexto quando relevantes, preservando tokens.

---

## 2. Canais de Mensageria (Agnósticos)

O ORION não é restrito à sua própria interface. O usuário pode habilitar conectores de canais opcionais:

```
┌────────────────────────────────────────────────────────┐
│                      ORION Core                        │
└───────────────────────────┬────────────────────────────┘
                            │ Channel Adapter Interface
                            ▼
    ┌───────────────┬───────────────┬───────────────┐
    ▼               ▼               ▼               ▼
[Telegram]     [WhatsApp]      [Discord]       [Webhooks]
(Bot API)     (Gateway API)    (Bot API)       (HTTP Genérico)
```

- Cada canal atua como uma **superfície de entrada e saída**.
- Todas as mensagens trafegam com a mesma segurança e governança (PEP).
- A Linha do Tempo e a Memória são as mesmas, independente do canal de onde o usuário enviou a mensagem.

---

## 3. Contrato de Agentes Satélites (HTTP)

Qualquer agente externo desenvolvido pelo usuário ou por terceiros pode ser orquestrado pelo ORION desde que exponha dois endpoints padronizados:

- `GET /health` ou `/info`: Retorna o status do satélite e a lista de capacidades disponíveis (`capabilities: ["acao1", "acao2"]`).
- `POST /execute`: Recebe `{ task_id, intent, payload, context }` e retorna o resultado estruturado em JSON `{ status, result, error }`.

Dessa forma, o ORION pode orquestrar fluxos no n8n, serviços em FastAPI ou qualquer outro bot sem misturar seu código-fonte com sistemas externos.
