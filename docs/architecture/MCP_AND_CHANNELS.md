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

### 1.1 Cliente MCP completo (v0.5.0 Sprint 5B)

* **Transportes:** `stdio`, `sse` e `http` (streamable HTTP). Headers por servidor aceitam `${VAR}` (variável ausente é erro; o segredo nunca é enviado vazio nem precisa ficar no arquivo). URL remota: só `http(s)`, sem credenciais embutidas, e credenciais (headers/OAuth) só por `https` ou loopback.
* **OAuth 2.1 (PKCE S256):** descoberta, registro dinâmico, `resource` e refresh pelo SDK `mcp`. Tokens em `~/.orion/mcp_auth/<servidor>.json` (diretório 0700, arquivo 0600, escrita atômica). O boot **nunca abre o navegador**: sem token o servidor fica em erro com `/mcp auth <srv>`; o login usa um callback em `127.0.0.1` (porta efêmera, só `/callback`).
* **Resources:** `@servidor:uri` na mensagem injeta o conteúdo como `<mcp_resource trust="untrusted">` (delimitadores forjados neutralizados, limite de 20 mil caracteres, no máximo 5 por turno); tools sintéticas `list_mcp_resources` e `read_mcp_resource` (LEVEL_1).
* **Prompts:** viram slash commands `/mcp__<srv>__<prompt>`; argumentos posicionais ou `chave=valor`.
* **Resiliência:** `list_changed` (tools, resources, prompts) atualiza o catálogo e incrementa a geração do cliente (a sessão re-registra as tools por geração, não por contagem de servidores); keepalive por ping (rede apenas, zero tokens); queda de conexão reconecta com backoff exponencial limitado (padrão 5 tentativas), exceto falha inicial e perda de login, que não ficam em loop.
* **Comandos:** `/mcp add|remove|auth|resources|prompts` além de `list|enable|disable|ping|tools`. `mcp_servers.json` é gravado de forma atômica com 0600; stdio novo passa pela allowlist de launchers.
* **Governança:** toda tool MCP continua passando pelo PEP (LEVEL_1 só se declarada somente leitura; senão LEVEL_2). Nenhum hook, regra ou plugin aprova nada por conta própria.

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
