# Sprint — v0.5.3 Sprint 5: Consolidação e recall

> **Status:** 📋 Aguardando comando de início · **ADR:** 050, 051 · **Achados:** M-03, M-05, M-06 · **CA:** CA-11 (cartão completo), CA-14, CA-21 a CA-24 · **Emenda:** 16/11/2026 (pendências proativas, perfil do Senhor, turnos indexados, PT-BR, purge)

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

8. **Pendências e proatividade** (`memory/commitments.py`, determinístico na superfície):
   - Tabela `commitments(id, text, kind todo|promise|followup|reminder, due_at NULL, scope, workspace NULL, session_id, evidence_ref, status open|done|dropped, created_at, surfaced_at, closed_at)`.
   - Origem: `open_items` dos cartões; pedido explícito ("me lembra", "depois a gente vê X"); promessa do próprio ORION ("verifico depois"). O Mordomo cria e fecha (`done` quando o delta mostra conclusão, com `evidence_ref`); o Senhor fecha por `/memory pending`.
   - **Abertura da daily:** bloco "Pendente" (até 5 itens, ordenados por prazo e idade) no início da daily, montado sem LLM, dentro do core congelado (teto próprio de 200 tokens).
   - **Entrada num workspace:** ao abrir thread num diretório, o core inclui a última thread daquele workspace (título + 1 linha do cartão) e as pendências com `workspace` igual. Zero token extra fora do core.
   - **Prazo:** pendência com `due_at` cria um agendamento no scheduler da v0.5.0 (faixa Livre, notifica pelo roteador); sem daemon ligado, aparece no próximo início de sessão. Nunca dispara ação mutante, só lembra.
   - Pendência aberta há 30 dias sem toque é perguntada uma vez ("ainda vale?") no cartão da daily.
9. **Perfil do Senhor** (`memory/profile.py`):
   - Gerado pelo Reflector na primeira atividade de cada semana (e por `/memory profile rebuild`), a partir de fatos CONFIRMED, PROVISIONAL com evidência, sinais agregados e rollups da semana.
   - Seções fixas: como trabalha, como prefere respostas, stack e ferramentas, ritmo/horários, o que evitar, em andamento. Teto 400 tokens, dentro do core (o teto do core sobe de 1.200 para 1.600 tokens: perfil 400 + resto 1.200).
   - **Toda frase cita ids** de fatos ou sinais; o código descarta frase sem ref válida. Inferência do perfil nunca vira fato CONFIRMED.
   - `/memory profile` mostra e edita; trechos editados pelo Senhor ficam marcados e o Reflector não os reescreve.
10. **Turnos indexados** (corrige "guardado mas não achado"): tabela `turns_fts` (FTS5) com as mensagens do Senhor, respostas finais e observações locais, por sessão e com hora; vetores dos mesmos turnos quando o modelo multilíngue estiver instalado. `session_search` combina cartões/rollups (peso maior) e turnos, e devolve trecho + `session_id` + `turn_id` para `session_read`. Atualização incremental a cada turno; migração indexa os JSONL existentes.
11. **PT-BR sem o modelo**: FTS5 com `tokenize='unicode61 remove_diacritics 2'` e uma coluna normalizada por um stemmer leve em Python puro (plural, gênero, diminutivo e sufixos verbais regulares, no estilo RSLP-S) aplicado no índice e na consulta; consultas usam prefixo. Ganho limitado ao morfológico; o semântico vem do modelo.
12. **Oferta do modelo multilíngue**: na primeira sessão interativa sem o modelo, uma pergunta única na TUI ("Instalar o modelo de memória multilíngue (~220 MB, local)? s/N"). "s" é a ação explícita exigida pelo ADR-040 e roda `/memory model install` em segundo plano; "N" é lembrado e só reaparece no `/doctor`. Nunca baixa sem resposta.
13. **Esquecer de verdade**: `/memory forget` continua DEPRECATED (reversível). `/memory purge <id|busca>` mostra o que vai sumir e, com confirmação, apaga fato, evidências, vetores, linhas FTS e menções no perfil; a auditoria registra só `memory_purge: N itens`, sem conteúdo. "Esquece isso de verdade" na conversa vira pedido de purge com confirmação.

## Testes
- `tests/unit/test_rollups.py`, `test_reflector.py`, `test_vector_sqlite_vec.py`, `test_session_search.py`.
- `tests/unit/test_commitments.py` (origem, fechamento com evidência, agendamento por prazo, pergunta dos 30 dias), `test_profile.py` (frase sem ref descartada, trecho do Senhor preservado, teto), `test_turns_index.py`, `test_ptbr_stem.py`, `test_memory_purge.py` (nada resta em nenhum índice).
- `tests/memory_eval/`: pergunta temporal (CA-14), fato de ontem em outra sessão, cartão da daily, pendência na daily e no workspace (CA-21), perfil com fontes (CA-22), detalhe fora do cartão achado por turno (CA-23), purge (CA-24).

## Critérios de saída
CA-11, CA-14 e CA-21 a CA-24 verdes; commit `feat(memory): v0.5.3 Sprint 5 — consolidação e recall`.
