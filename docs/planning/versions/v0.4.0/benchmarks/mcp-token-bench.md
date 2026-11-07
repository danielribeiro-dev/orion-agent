# Benchmark — custo em tokens do starter pack MCP (2026-11-06)

**Método:** determinístico, sem LLM. Mede os tokens (heurística de 4 caracteres/token do próprio ORION) que o modelo *receberia* por tarefa de navegação de código, comparando o caminho nativo (`grep` + `read_file` do arquivo inteiro) com o Serena 2.1.0 (modo `tools`, via `MCPClient` real). Repositório: cópia de `src/` do ORION. Script: `scripts/bench_mcp_tokens.py` (rodar dentro de um projeto com `.serena/project.yml` criado via `serena project create --language python`).

## Overhead fixo por turno (10 tools visíveis: Serena 8 + Context7 2)
| Modo | Tokens |
|---|---|
| Schemas completos | ~4284 |
| Catálogo lazy (1 linha por tool, `mcp_schema` sob demanda) | ~272 |
| `TOOL_PROTOCOL` base do ORION | ~135 |

## Custo por tarefa
| Tarefa | Nativo | Serena | Variação |
|---|---:|---:|---:|
| T1 definição + callers de `PolicyEnforcementPoint.evaluate` | 5108 | 902 | -82% |
| T2 estrutura de `tui/session.py` | 7423 | 263 | -96% |
| T3 usos de `tool_action_level` | 56 | 134 | **+139% (pior)** |
| T4 corpo de `MCPClient.call_tool` | 2207 | 253 | -89% |
| Total | 14794 | 1552 | -90% |

## Leitura honesta
- O ganho existe quando a alternativa é **ler arquivo inteiro** (T1, T2, T4). Para busca trivial por `grep` (T3) o Serena é mais caro.
- O baseline é ingênuo: um agente real costuma ler trechos (`offset`/`limit`) e o ORION ainda não os tem. O ganho em produção tende a ser menor que 90%.
- **Não mede qualidade nem acerto de tarefa**, nem tokens de raciocínio do modelo. Um A/B ponta a ponta com LLM continua pendente (custa créditos).
- Não medido: latência. Conexão do Serena ~2 s; Context7 ~10 s no primeiro uso (download do npm).
- Primeira tentativa do benchmark foi invalidada: sem `language_servers` no `.serena/project.yml` (a autodetecção de linguagem retornou `[]` na cópia em /tmp), todas as chamadas do Serena davam erro e o "ganho" de 99% era só o tamanho da mensagem de erro.

## Riscos de produto descobertos
- Serena grava `.serena/` no workspace do usuário e pode falhar sem linguagem detectada. O `/mcp` precisa mostrar o erro (já mostra o status do servidor, mas não o erro por chamada).
- Serena 2.1.0 usa por padrão a interface `repl` (tool `serena_repl` executa Python com `shell`/`edit`). O catálogo força `--agent-interface tools` e esconde as tools de edição e de memória.

## A/B com LLM real (parcial, 2026-11-06)
**Setup:** `AgentSession` do ORION em modo Plan (somente leitura), modelo `nvidia/nemotron-3-ultra-550b-a55b:free` (OpenRouter, tier gratuito), 1 repetição, braço A = sem MCP, braço B = starter pack ligado. Acerto verificado por substring. Script: `scripts/ab_mcp_llm.py`.

| Tarefa | Braço | Tokens in | Tokens out | Tools (MCP) | Acerto |
|---|---|---:|---:|---:|---:|
| T1 definição de `evaluate` | A | 3587 | 494 | 2 (0) | 1.00 |
| T1 | B | 11225 | 990 | 8 (7) | 1.00 |
| T2 métodos de `MCPClient` | A | 3059 | 300 | 1 (0) | 1.00 |
| T2 | B | 3662 | 299 | 1 (0) | 1.00 |
| T3, T4 | A/B | — | — | — | **inválidas**: 429 do tier gratuito (0 tokens, ~150 s de espera) |

**Leitura honesta**
- Apenas 4 de 8 execuções são válidas; n=1 por célula, um único modelo gratuito. **Não há conclusão estatística.**
- Nada aqui confirma economia de tokens. Em T1 o braço B gastou ~3x mais tokens de entrada: o modelo chamou `search_for_pattern` 7 vezes em vez de `find_symbol`. Em T2 o B só pagou o catálogo (~600 tokens a mais) sem usar MCP.
- O que o teste valida é a integração: o ORION conectou o Serena, listou as tools no prompt, o PEP liberou as de leitura e o modelo as chamou com sucesso.
- O A/B encontrou 2 bugs de produto na tool nativa `search_files` e no prompt (modo `content` inexistente; grep sem `regex` ou com `path` de arquivo nunca achava nada), já corrigidos com testes. Antes dessa correção o braço A afirmava que classes existentes "não existem".
- Para uma conclusão, repetir com modelo pago, ≥5 repetições e mais tarefas.
