# Sprint — v0.5.3 Sprint 3: Sessões e daily

> **Status:** 📋 Aguardando comando de início (pode começar depois da Sprint 1) · **ADR:** 051 · **Achados:** M-08, M-09, M-10 · **CA:** CA-11 a CA-13

## Objetivo
Organizar a vida do ORION em dailies e sessões com título, achadas por nome e por data, e dar à voz uma sessão padrão estável.

## Escopo
1. **Índice** `~/.orion/sessions.db` (`sessions/index.py`):
   - Tabela `sessions(id, kind daily|thread, title, title_source auto|user, daily_id, parent_id, workspace NULL, created_at, updated_at, closed_at, turn_count, card_json)`, FTS5 sobre `title` e `card`, índices por data local.
   - Os JSONL continuam o transcript; o índice é atualizado a cada turno (sem reler arquivos). `SessionStore.list()` passa a consultar o índice.
   - Migração idempotente dos JSONL existentes (título = prévia do primeiro pedido, `kind=thread`, `daily_id` pela data), com backup em `~/.orion/backup/v0.5.2/`.
2. **Títulos**: título provisório determinístico (primeiro pedido, 60 caracteres); título definitivo pelo Mordomo na Sprint 4 (ou no fechamento). `/rename <título>` grava `title_source=user`, que nunca é sobrescrito.
3. **Daily**:
   - Id `daily-YYYY-MM-DD` (data local), estável; o daemon e a voz sem TUI usam a daily do dia (corrige M-09).
   - Virada: `settings.memory.day_starts_at` (padrão `04:00`) ou primeira atividade depois dela. Na virada: fecha a daily anterior (gera cartão na Sprint 5; nesta sprint, cartão determinístico com contagens e títulos das threads) e abre a nova com o resumo curto da anterior (até 300 tokens).
   - `orion --daily` e TUI aberta em `~` anexam à daily.
4. **Threads**:
   - TUI aberta num diretório que não é `~` cria uma thread com `daily_id` do dia; a daily ganha um evento-link.
   - Tool `session_branch(title, reason)` (faixa Livre): abre uma thread a partir da conversa atual, copia o contexto mínimo (últimos 2 turnos + resumo), registra o link na daily e passa a sessão ativa para ela. Tool `session_switch(query)` volta para uma sessão pelo nome ou data.
   - `/merge` e branches passam a ser threads persistidas (substituem `BranchManager` em RAM; `~/.orion/timeline/archive` migrado).
5. **`/resume`** (`tui/commands/resume.py` + `tui/completer.py`):
   - Seletor em overlay com campo de busca. Filtros reconhecidos: `hoje`, `ontem`, `semana`, `semana passada`, `mês`, nome de mês (`nov`, `novembro`), `2026-11`, `2026`, `16/11`, `daily`, `thread`, `@<workspace>`; o resto é busca FTS no título e no cartão.
   - Árvore ano › mês › dia, com a daily e suas threads aninhadas; Enter retoma.
   - Global por padrão; `@.` filtra o workspace atual. `--resume <prefixo>` e `--continue` mantidos.

## Testes
- `tests/unit/test_sessions_index.py` (migração, FTS, filtros de data com fuso), `test_daily.py` (virada, id estável, resumo), `test_session_branch.py`.
- Lab: `/resume` com `ontem` e `nov`, árvore e retomada.

## Critérios de saída
CA-11 a CA-13 verdes (o cartão completo chega na Sprint 5); commit `feat(memory): v0.5.3 Sprint 3 — sessões e daily`.
