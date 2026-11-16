# Sprint — v0.5.3 Sprint 5: Consolidação e recall

> **Status:** 📋 Aguardando comando de início · **ADR:** 050, 051 · **Achados:** M-03, M-05, M-06 · **CA:** CA-11 (cartão completo), CA-14

## Objetivo
Fazer a memória consolidar em vez de acumular e responder perguntas sobre o passado do geral para o detalhe.

## Escopo
1. **Cartões de sessão** (`memory/rollups.py`): no fechamento de thread e daily, o Mordomo gera `{title, topics[], decisions[], open_items[], learned[], files[], summary}` (até 250 tokens) gravado em `sessions.card_json` e no FTS. Título definitivo da thread sai daqui quando `title_source=auto`.
2. **Rollups**: dia (das threads + daily), semana, mês e ano, gerados por evento (virada do dia, primeira atividade da semana/mês) a partir dos cartões, nunca do transcript bruto. Tabela `rollups(period, start, end, summary, refs)` com FTS.
3. **Reflector**: na virada do dia, o Mordomo revisa fatos tocados no dia: funde duplicatas (`supersedes`), promove PROVISIONAL com evidência, rebaixa fatos sem uso há 90 dias da prioridade do core (sem apagar).
4. **Embeddings multilíngues**: `paraphrase-multilingual-MiniLM-L12-v2` via fastembed, instalado por `/memory model install` (ADR-040); reindexação em lote por evento; `bge-small-en` continua como reserva até a reindexação terminar.
5. **`sqlite-vec`** substitui a varredura NumPy (M-06); conexões reaproveitadas por sessão.
6. **Recuperação do geral para o detalhe**:
   - Tool `session_search(query, since?, until?, kind?)` (Livre, sem LLM): busca em rollups e cartões, devolve sessões com trechos; `session_read(id, around?)` rola dentro do transcript.
   - `recall` ganha `since/until` e entende "semana passada", "ontem", "em outubro".
   - Auto-recall por turno inclui o rollup do dia anterior quando o pedido tem marca temporal.
7. **`/memory`**: editar, esquecer (DEPRECATED com `source=user`), fila de revisão dos PROVISÓRIOS (confirmar/descartar em lote), ver linhagem de um fato, exportar JSON.

## Testes
- `tests/unit/test_rollups.py`, `test_reflector.py`, `test_vector_sqlite_vec.py`, `test_session_search.py`.
- `tests/memory_eval/`: pergunta temporal (CA-14), fato de ontem em outra sessão, cartão da daily.

## Critérios de saída
CA-11 e CA-14 verdes; commit `feat(memory): v0.5.3 Sprint 5 — consolidação e recall`.
