# Sprint — v0.5.3 Sprint 4: Escrita e core

> **Status:** 📋 Aguardando comando de início · **ADR:** 050 · **Achados:** M-01, M-02, M-04, M-07, M-11 · **CA:** CA-09, CA-10, CA-18, CA-19, CA-20, CA-26 · **Emenda:** 16/11/2026 (evidência ancorada, observações locais, sinais implícitos; histórico visível ao entrar numa sessão, pedido do Senhor após a Sprint 3)

## Objetivo
Fazer a memória ser escrita sem depender do modelo principal e garantir que o essencial esteja sempre presente.

## Escopo
0. **Histórico visível ao entrar numa sessão** (pedido do Senhor em 16/11/2026; independente do resto, implementar primeiro):
   - Problema: ao entrar numa sessão (daily em `~`, `--resume`, `--continue`, `/resume`, `session_branch`/`session_switch`, `/merge`, virada do dia) a conversa é carregada no contexto do modelo, mas a tela mostra só uma linha de aviso. Já existia desde o `--resume` da v0.5.0; a Sprint 3 o tornou constante, porque toda TUI aberta em `~` entra na daily.
   - Alvo: recarregar **tudo**, como Claude Code e Antigravity fazem. A transcrição mostra a sessão inteira desde o primeiro pedido: pedidos do Senhor, respostas, cartões de tool (recolhidos, com a saída do `tool_result` ao abrir), diffs de arquivos, linhas do PEP e avisos. O visual é o mesmo de um turno ao vivo.
   - **Exibição não é contexto:** a tela é montada a partir das entradas cruas do JSONL (`message`, `file_change`, eventos `meta`), não do `replay`. Depois de uma compactação, o que o modelo vê é o resumo, mas na tela os turnos antigos continuam visíveis, com uma linha `· contexto compactado aqui (o modelo vê o resumo)` no ponto do corte. A semente de thread ou daily aparece como bloco recolhido (`› contexto herdado de ...`). O link `thread_opened` na daily aparece como linha `› thread aberta: <título>`.
   - Tela cheia: as células da transcrição são criadas sob demanda (virtualização: só se rasteriza o que entra na janela e o reflow é preguiçoso), para que uma daily com centenas de turnos abra em menos de 300 ms. O Ctrl+O e a busca alcançam todo o histórico.
   - Modo clássico: o histórico é impresso no scrollback antes do prompt, com os mesmos cartões.
   - Custo zero: leitura local do JSONL, nenhuma chamada ao modelo.
   - Arquivos: `sessions/transcript.py` (função de exibição sobre as entradas cruas), `tui/screen/transcript.py` e `app.py` (carga do histórico e virtualização), `tui/sink.py`/`RichSink` (modo clássico) e `AgentSession._apply_switch`/`resume` (um único ponto que redesenha).
1. **Fatos v2** (`memory/facts_store.py`, migração):
   - Colunas novas: `scope global|org|project|device`, `scope_ref`, `status CONFIRMED|PROVISIONAL|DEPRECATED` (INFERRED vira PROVISIONAL), `confidence`, `evidence_count`, `source user|steward|tool|import`, `session_id`, `valid_from`, `valid_to`, `supersedes`, `superseded_by`; horas sempre com fuso (M-11).
   - Categorias abertas (texto livre com sugestões), FTS5 sobre `key + value`.
   - Fato superado ganha `valid_to` e `superseded_by`; nada é apagado (ADR-027), salvo `purge` explícito do Senhor (Sprint 5).
   - Tabela `fact_evidence(fact_id, session_id, ref_kind user_msg|tool_obs|signal, ref_id, created_at)`: cada fato aponta para as provas que o sustentam.
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
   - Entrada: delta do transcript desde a última execução (mensagens do Senhor e respostas finais, cada uma com id estável) + **observações locais** (item 4a) + sinais implícitos pendentes (item 4b, resumidos) + até 20 fatos vizinhos pela busca híbrida + o core atual.
   - Saída JSON validada por Pydantic: lista de `{op: ADD|UPDATE|SUPERSEDE|CONFIRM|NOOP, key, value, scope, confidence, evidence_refs[], valid_from}`.
   - **Evidência ancorada (corrige o risco de autoconfirmação):** toda op diferente de NOOP precisa de `evidence_refs` com ids que existam **neste delta**. O código valida: fato sobre o Senhor (`scope=global`) só aceita `user_msg`; fato `project|device` aceita também `tool_obs`; `signal` sozinho nunca basta (só reforça). Op sem ref válida é descartada e contada em `steward_rejected`. O Mordomo nunca vê o id de evidências antigas, então não consegue "reafirmar" um PROVISIONAL sem prova nova.
   - Regras duras aplicadas no código, não no prompt: pedido explícito do Senhor => CONFIRMED; inferência => PROVISIONAL; nunca sobrescrever CONFIRMED com inferência (vira pergunta pendente ao Senhor); PROVISIONAL vira CONFIRMED só com **refs `user_msg` distintas em 3 sessões distintas** (contadas em `fact_evidence`, não em `evidence_count` declarado pelo modelo); conteúdo vindo de web/MCP nunca vira fato (nem sobre o Senhor, nem sobre projeto).
4a. **Observações locais** (`memory/observations.py`): saídas de tools de leitura local (`read_file`, `search_files`, `list_dir`, `run_command` classificado como leitura: `git log/status/remote`, `cat`, `uname`, `lsblk`, `nvidia-smi`, `python --version`...) geram uma observação compacta por chamada: caminho/comando + até 12 linhas relevantes escolhidas deterministicamente (arquivos de manifesto como `pyproject.toml`, `package.json`, `docker-compose*`, `.env.example` e versões têm prioridade). Entram no delta com id `tool_obs:<id>` e podem fundamentar fatos `scope=project|device` (`source=tool`). Saídas de `web_*` e de MCP nunca viram observação.
4b. **Sinais implícitos** (`memory/signals.py`, determinístico, zero token): tabela `signals(id, kind, subject, detail, session_id, ts)` alimentada por eventos que o ORION já produz:
   - PEP: aprovado, negado, "sempre" (assinatura do comando ou caminho);
   - `/undo` e "desfazer" de uma linha "aprendi";
   - **edição do Senhor sobre escrita do agente:** no fim de cada turno o ORION guarda hash dos arquivos que escreveu; no turno seguinte e no fechamento compara; se mudou sem tool do ORION, grava o diff resumido (até 20 linhas);
   - interrupção (Esc) seguida de reformulação; resposta reescrita pelo Senhor ("mais curto", "sem tabela");
   - horário e duração de atividade por dia (só agregados).
   Sinais entram resumidos no Mordomo (podem fundamentar PROVISIONAL só junto com uma `user_msg`) e alimentam o perfil da Sprint 5. Nunca saem da máquina além do resumo enviado ao Mordomo.
   - Modelo: tier BALANCED-barato (classe Haiku/Flash) via router; reserva free; nunca cair silenciosamente para FAST/local (ADR-031): sem modelo adequado, adia. Teto diário `origin=memory`.
5. **Transparência**: linha `● aprendi: <fato> · desfazer` no fim do turno seguinte (tecla `u` desfaz = DEPRECATED com `source=user`); por voz/daemon, acumula para o cartão da daily ("hoje aprendi").
6. **Diretivas permanentes**: fato `category=directive` com gatilho exato (determinístico, zero token) ou semântico; avaliadas antes do turno; ações mutantes passam pelo PEP.
7. **Recall fora do transcript** (M-07): `<recalled_context>` é injetado na chamada e não persistido; o transcript guarda só a referência (ids).
8. **Auto-recall**: fatos por FTS5 no lugar da substring; exclui o que já está no core.

## Testes
- `tests/unit/test_session_history_view.py`: exibição montada das entradas cruas (compactação não esconde turnos antigos e marca o corte; semente e link aparecem; tool recolhida com saída); `/resume`, troca por `session_switch` e virada redesenham. Lab: `test_resume.py` estendido (depois de retomar, o primeiro pedido da sessão aparece ao rolar para cima e no Ctrl+O; daily com 300 turnos sintéticos abre em menos de 300 ms).
- `tests/unit/test_facts_v2.py` (migração, linhagem, tempo), `test_core_block.py` (teto, ordem, congelamento), `test_salience.py`, `test_steward.py` (provider roteirizado: correção vira SUPERSEDE; inferência PROVISIONAL; CONFIRMED protegido; web nunca vira fato do Senhor).
- `tests/unit/test_fact_evidence.py` (op sem ref descartada; ref inventada descartada; reafirmação sem prova nova não promove; promoção só com 3 sessões distintas de `user_msg`), `test_observations.py` (seleção determinística de linhas; web/MCP excluídos), `test_signals.py` (PEP, `/undo`, edição do Senhor detectada por hash).
- `tests/memory_eval/` começa aqui: identidade sem tool (CA-09), correção (CA-10), autoconfirmação bloqueada (CA-18), fato de projeto por leitura local (CA-19), preferência por sinal implícito + fala (CA-20).

## Critérios de saída
CA-26, CA-09, CA-10, CA-18, CA-19 e CA-20 verdes; commit `feat(memory): v0.5.3 Sprint 4 — escrita e core`.
