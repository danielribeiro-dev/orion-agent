# Sprint — v0.5.3 Sprint 3: Sessões e daily

> **Status:** ✅ Implementada em 16/11/2026 · **ADR:** 051 · **Achados:** M-08, M-09, M-10 · **CA:** CA-11 a CA-13

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

## Registro de execução (16/11/2026)
Entregue conforme o escopo. Validação: suíte padrão, testes novos de índice, daily e threads, e o cenário de lab do `/resume` num PTY real em tela cheia.

- **Índice** (`sessions/index.py`): `~/.orion/sessions.db` (0600, WAL) com a tabela do escopo mais `local_date` (data da daily, já deslocada pela virada) e `opening` (resumo de abertura); FTS5 `unicode61 remove_diacritics 2` sobre título e cartão (`sessao` acha `sessão`), índices por data, daily e workspace. Atualizado a cada pedido (`record_turn`), sem reler arquivos. `JsonlSessionStore.list()` consulta o índice; sem ele, varre como antes. Sessões sem pedido ficam fora da busca.
- **Migração** idempotente na primeira abertura: JSONL da v0.5.2 viram threads (título = primeiro pedido, `daily_id` pela data local) e as branches de `timeline/archive` viram threads fechadas com transcript mínimo em `sessions/archive/` (retomáveis). Backup em `~/.orion/backup/v0.5.2/` (0700) antes de indexar, uma vez.
- **Títulos**: provisório determinístico (primeiro pedido, até 60 caracteres sem cortar palavra); `set_auto_title` (para o Mordomo na Sprint 4) nunca vence o `/rename`.
- **Daily** (`sessions/daily.py`, `sessions/clock.py`): `daily-YYYY-MM-DD` pela data local deslocada por `memory.day_starts_at` (padrão 04:00, novo bloco `memory` no settings). A virada roda na primeira atividade (nunca por relógio): fecha todas as dailies abertas de dias anteriores com cartão determinístico (pedidos, threads com títulos e contagens, primeiros pedidos, resumo) e abre a nova com o resumo da anterior (teto de 1.200 caracteres, ~300 tokens), gravado como semente no transcript. TUI em `~`, `--daily`, daemon e voz anexam à daily; a TUI aberta na daily acompanha a virada no pedido seguinte.
- **Threads** (`sessions/navigator.py`): TUI fora de `~` registra a thread no primeiro pedido, com `daily_id` do dia e um evento-link (`thread_opened`) no transcript da daily. Tools `session_branch(title, reason)` e `session_switch(query)` (faixa Livre, LEVEL_0, nunca dadas a subagents). `/branch` e `/merge` passam a ser threads persistidas: `/merge` fecha a thread com checkpoint no cartão e volta ao pai só com ele. `BranchManager` removido.
- **`/resume`** (`tui/commands/resume.py`) com `/rename`: seletor em overlay com campo de busca, filtros do escopo (`hoje`, `ontem`, `semana`, `semana passada`, `mês`, nomes de mês, `2026-11`, `2026`, `16/11`, `16/11/2026`, `daily`, `thread`, `@.`, `@nome`), o resto em FTS; árvore ano › mês › dia com a daily e as threads aninhadas; Enter retoma. `/resume <id>` retoma direto; `/resume <filtro>` abre o seletor já filtrado; sem terminal, imprime a árvore. `--resume` e `--continue` mantidos (em `~`, `--continue` retoma a daily anterior).

### Desvios e decisões tomadas na execução
1. **`session_branch` e `session_switch` trocam de sessão ao fim do turno**, não no meio: o turno corrente fica inteiro na origem (cada `tool_use` com seu `tool_result`), e a thread nasce com os últimos 2 turnos, que já incluem esse. Turno falho ou cancelado descarta a troca; uma segunda troca no mesmo turno é recusada.
2. **Evento-link sem número** (`append_event`, `index=-1`): outro processo (daemon, outra TUI) pode estar escrevendo na daily; o evento não usa o contador local, o `replay` o ignora e o `rewind` o preserva.
3. **Agendamentos (`origin=cron`) nunca anexam à daily**, mesmo com workspace `~`: continuam sessões limpas.
4. **Daily antiga retomada não segue a virada**: só a daily anexada automaticamente pula para o dia novo.
5. **Thread nasce no índice no primeiro pedido** (nada de thread vazia ao só abrir a TUI); `/rename` antes do primeiro pedido a registra.
6. **`/branch <título>`** aceita texto livre (antes só slug); repetir o título da thread ativa não abre outra.
7. **Correção na tela cheia (achada pelo lab)**: com um modal aberto o input fica somente leitura, o que ligava os atalhos "estilo less" do prompt_toolkit (`n`, `N`, `/`, `?`) e engolia essas teclas em qualquer modal, inclusive no filtro do `/model`. O modal agora os declara como atalhos exatos (`tui/screen/app.py`).
8. Título da daily: `Daily 16/11/2026 (segunda)`. No seletor, `●` marca a daily, `›` a thread e `✔` a sessão ativa.

### Validação
- Suíte: 2482 testes passando (15 pulados), cobertura 93%; lab 29/29 (28 antigos + `test_resume.py`); `ruff` e `mypy` limpos.
- Novos: `test_sessions_index.py` (índice, FTS, títulos, filtros de data com fuso de São Paulo e virada às 04:00, migração com backup e idempotência, branch arquivada retomável), `test_daily.py` (id estável, virada com cartão e resumo, teto do resumo, daemon na daily e cron fora, `--daily`, link na daily, virada com a TUI aberta, `day_starts_at` do settings), `test_session_branch.py` (tools com modelo roteirizado, recarga da thread, `/branch` e `/merge`, `/rename`, árvore e seletor, `/resume` com filtros); lab `test_resume.py` (`/resume`, `ontem`, `nov`, árvore e retomada).
- **CA-11 ✅, CA-13 ✅; CA-12 ✅ com modelo roteirizado** (a decisão do modelo real de abrir a thread vai para `tests/memory_eval/` na Sprint 6). O cartão por modelo chega na Sprint 5.
