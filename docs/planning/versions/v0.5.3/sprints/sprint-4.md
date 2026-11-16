# Sprint — v0.5.3 Sprint 4: Escrita e core

> **Status:** 📋 Aguardando comando de início · **ADR:** 050 · **Achados:** M-01, M-02, M-04, M-07, M-11 · **CA:** CA-09, CA-10

## Objetivo
Fazer a memória ser escrita sem depender do modelo principal e garantir que o essencial esteja sempre presente.

## Escopo
1. **Fatos v2** (`memory/facts_store.py`, migração):
   - Colunas novas: `scope global|org|project|device`, `scope_ref`, `status CONFIRMED|PROVISIONAL|DEPRECATED` (INFERRED vira PROVISIONAL), `confidence`, `evidence_count`, `source user|steward|tool|import`, `session_id`, `valid_from`, `valid_to`, `supersedes`, `superseded_by`; horas sempre com fuso (M-11).
   - Categorias abertas (texto livre com sugestões), FTS5 sobre `key + value`.
   - Fato superado ganha `valid_to` e `superseded_by`; nada é apagado (ADR-027).
2. **Core** (`memory/core_block.py`, substitui `manifest.py` no prompt):
   - Montado no início da sessão e congelado (cache de prompt). Ordem: identidade do Senhor (nome, tratamento, idioma), diretivas permanentes, fatos CONFIRMED `global` por relevância e recência, fatos CONFIRMED do projeto atual. Teto 1.200 tokens, com corte por prioridade.
   - Inclui uma linha de política: o que lembrar e que o `memorize` existe, sem exigir uso.
   - Mudanças durante a sessão entram no próximo core; no turno corrente, a linha "aprendi" (item 5) já mostra ao modelo.
3. **Detector de saliência** (`memory/salience.py`, determinístico, sem rede):
   - Sinais com pesos: pedido explícito ("lembra", "anota", "a partir de agora", "sempre que", "me chame de") = disparo imediato; correção ("não, é", "na verdade", "errado"); primeira pessoa com preferência ou decisão ("eu prefiro", "vamos usar", "nunca", "sempre"); entidades (caminhos, hosts, versões, nomes próprios); similaridade de embedding com protótipos (quando o modelo local existir).
   - Acumulador por sessão; limiar padrão configurável em `settings.memory.salience_threshold`.
   - Não extrai nada; só decide quando o Mordomo roda.
4. **Mordomo** (`memory/steward.py`, porta `MemoryStewardPort`, roda em task de fundo):
   - Gatilhos: disparo imediato; saliência acima do limiar; a cada 8 turnos com saliência > 0; 2 min ocioso com delta pendente; fechamento da sessão.
   - Entrada: delta do transcript desde a última execução (só mensagens do Senhor e respostas finais; saídas de tool resumidas a uma linha) + até 20 fatos vizinhos pela busca híbrida + o core atual.
   - Saída JSON validada por Pydantic: lista de `{op: ADD|UPDATE|SUPERSEDE|CONFIRM|NOOP, key, value, scope, confidence, evidence, valid_from}`.
   - Regras duras aplicadas no código, não no prompt: pedido explícito do Senhor => CONFIRMED; inferência => PROVISIONAL; nunca sobrescrever CONFIRMED com inferência (vira pergunta pendente ao Senhor); PROVISIONAL com `evidence_count >= 3` em sessões distintas => CONFIRMED; conteúdo vindo de web/MCP nunca vira fato sobre o Senhor.
   - Modelo: tier BALANCED-barato (classe Haiku/Flash) via router; reserva free; nunca cair silenciosamente para FAST/local (ADR-031): sem modelo adequado, adia. Teto diário `origin=memory`.
5. **Transparência**: linha `● aprendi: <fato> · desfazer` no fim do turno seguinte (tecla `u` desfaz = DEPRECATED com `source=user`); por voz/daemon, acumula para o cartão da daily ("hoje aprendi").
6. **Diretivas permanentes**: fato `category=directive` com gatilho exato (determinístico, zero token) ou semântico; avaliadas antes do turno; ações mutantes passam pelo PEP.
7. **Recall fora do transcript** (M-07): `<recalled_context>` é injetado na chamada e não persistido; o transcript guarda só a referência (ids).
8. **Auto-recall**: fatos por FTS5 no lugar da substring; exclui o que já está no core.

## Testes
- `tests/unit/test_facts_v2.py` (migração, linhagem, tempo), `test_core_block.py` (teto, ordem, congelamento), `test_salience.py`, `test_steward.py` (provider roteirizado: correção vira SUPERSEDE; inferência PROVISIONAL; CONFIRMED protegido; web nunca vira fato do Senhor).
- `tests/memory_eval/` começa aqui: identidade sem tool (CA-09), correção (CA-10).

## Critérios de saída
CA-09 e CA-10 verdes; commit `feat(memory): v0.5.3 Sprint 4 — escrita e core`.
