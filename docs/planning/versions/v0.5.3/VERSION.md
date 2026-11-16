# Spec — v0.5.3 Memória Viva e Núcleo Livre

> **Status:** 📋 Sprint 0 (spec) concluída em 16/11/2026; Sprints 1 a 6 aguardam o comando de início do Senhor  
> **Criada em:** 2026-11-16  
> **Concluída em:** —  
> **Autor(es):** Daniel Dev & Claude (Pair Programming)  
> **Branch:** `feat/v0.5.3-memoria-viva` (criada de `feat/v0.5.2-bridge`)  
> **Pesquisa:** [`pesquisa-memoria-e-autonomia.md`](pesquisa-memoria-e-autonomia.md) (achados M-01 a M-12 e G-01 a G-10, comparativo e fontes)

---

## 1. Visão Geral & Motivação

### 1.1 Objetivo
Tornar a memória o ponto mais forte do ORION e tirar as amarras que o fazem parecer menor que Claude Code, Antigravity e Hermes:
- **Memória Viva:** ele lembra do Senhor sempre, aprende sem depender de o modelo chamar uma tool, consolida em vez de acumular, e organiza a vida em dailies e sessões que se acham por nome e por data.
- **Memória que conhece o Senhor (emenda de 16/11/2026):** traz pendências sem ser perguntado (daily e entrada em workspace), aprende com o que o Senhor faz e não só com o que diz (sinais implícitos), mantém um perfil curto com fontes, acha detalhe que o resumo não guardou, e prova a qualidade da extração com avaliação ao vivo.
- **Núcleo Livre:** ele mora no PC e age em todo o espaço do usuário. O PEP continua decidindo, mas por raio de destruição e reversibilidade; a presença do Senhor só é exigida para o que não tem volta.
- **Núcleo Enxuto:** primeiro turno abaixo de 6k tokens.

### 1.2 Por que agora?
A rodada real de 09/11/2026 terminou com `facts.db` vazio (R-06), a sessão seguinte não reconstruiu o tema anterior (R-07), o primeiro "pong" custou 14.871 tokens (R-16) e um subagent morreu num 429 sem reserva (R-17). O Senhor relatou que a senha do SO "não é reconhecida", que o ORION recusa ler/editar outro repositório e que fica preso a 11 sites. O diagnóstico (`pesquisa-memoria-e-autonomia.md` §1) mostrou causas concretas: a senha nunca é verificada (G-01), o `sudo` nunca tem por onde pedir senha (G-02), o ledger de confiança nunca foi ligado (G-05), a memória não tem caminho de escrita confiável (M-01) nem presença garantida (M-02). A voz (v0.6.0) depende disso: sem memória e sem autonomia, presença contínua não vale nada.

### 1.3 O que NÃO é escopo (anti-metas)
- Voz, wake word, STT/TTS (v0.6.0). Aqui só o lado de memória e sessão que a voz vai usar (daily, `session_branch`).
- Criação automática de skills a partir da experiência (v0.5.4).
- Banco de grafo, servidor externo de memória ou embeddings por rede (ADR-040 segue valendo).
- Memória portável cifrada e multi-dispositivo (v3.0.0); só o formato não pode impedir.
- Contornar o nuclear por qualquer via (hooks, subagents, agendamentos, regras, modo `full`).
- Chamada paga ou free em teste automático.

---

## 2. Decisões Arquiteturais & Diretrizes de Design

### 2.1 Padrões e Invariantes Aplicáveis
- Brain/Body: `orion.core` sem I/O; o Mordomo e o classificador rodam atrás de portas (`MemoryStewardPort`, `RiskClassifierPort`).
- PEP decide toda ação mutante; tool desconhecida = nível mais alto; nuclear nunca contornável.
- Segredos nunca no contexto do LLM, em logs ou na auditoria (ADR-042), inclusive a senha do SO.
- Ocioso = 0 tokens (ADR-022): consolidação e Mordomo só por evento, nunca por relógio sem atividade.
- Custos com teto no `BudgetGuard`, origem própria (`origin=memory`, `origin=classifier`).
- Doc-First, cobertura >= 85%, ruff e mypy strict, `asyncio`, SQL parametrizado.

### 2.2 Decisões do Senhor (16/11/2026)
1. Autonomia padrão "auto inteligente" (regras + classificador barato).
2. Último nível em escada por risco; senha verificada só para o irreversível que o ORION não consegue desfazer. O ORION pode lembrar a senha do sudo (no chaveiro do SO, opt-in) para que `sudo` não destrutivo rode sem pedir nada.
3. Busca web em cadeia plugável: Brave API → `ddgs` → SearXNG opcional.
4. TUI aberta num repositório = sessão nova ligada à daily do dia; em `~` ou com `--daily`, anexa à daily.
5. Memória escrita por um Mordomo em segundo plano disparado por saliência, não por regex extrator nem por cutucar o modelo principal.

### 2.3 ADRs desta versão
- **ADR-046:** Governança v2 — escopo do usuário, quatro faixas por reversibilidade, modos `plan/ask/auto/full`, classificador cego ao raciocínio, escalada para a Inbox.
- **ADR-047:** Motor de reversibilidade e aprovação por intenção.
- **ADR-048:** Senha verificada: askpass, chaveiro opt-in, polkit/PAM; fim do popup que aceita qualquer texto.
- **ADR-049:** Web aberta com blocklist, SSRF e sessão contaminada; `SearchProvider` em cadeia.
- **ADR-050:** Memória em cinco camadas, core congelado e Mordomo da Memória.
- **ADR-051:** Sessões indexadas, daily, threads e `/resume` por data.
- **ADR-052:** Núcleo enxuto: tools adiadas e cache de prompt.
- **Emendas:** ADR-006, 017, 018 [v0.3.0], 023 e 037 (registradas em `.claudex/decisions.md`).

### 2.4 Mudança proposta no `CLAUDE.md` (aplicar só na Sprint 1, com o código)
Linha **Segurança**, texto novo:
> **Segurança:** toda ação mutante passa pelo PEP (`governance/pep.py`), que decide por raio de destruição e reversibilidade (ADR-046); escopo = espaço do usuário, não o cwd. Ações nucleares exigem presença verificada (polkit/PAM, ADR-048) e nunca são contornáveis (hooks, subagents, agendamentos, regras ou modo `full`). Tool nova precisa de faixa PEP definida. A senha do SO nunca entra no contexto do modelo.

Até a Sprint 1, o `CLAUDE.md` atual continua valendo.

### 2.5 Dependências e Relações
- **Depende de:** v0.5.2 (tela cheia para overlays de senha e linha "aprendi"), v0.5.0 Sprint 7 (daemon, Inbox, notificações).
- **Desbloqueia:** v0.6.0 (voz usa a daily, o `session_branch` e a presença por voz), v0.5.4 (skills por experiência).

---

## 3. Divisão em Sprints & Entregáveis

| Sprint | Nome | Objetivo | Documento | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Sprint 0** | Spec | Pesquisa, VERSION, sprints, ADR-046 a 052 e emendas | [`sprint-0.md`](sprints/sprint-0.md) | ✅ |
| **Sprint 1** | Liberdade básica | Senha verificada (askpass, chaveiro, polkit/PAM, overlay), escopo do usuário, ledger ligado, web aberta + `SearchProvider` | [`sprint-1.md`](sprints/sprint-1.md) | 📋 |
| **Sprint 2** | Classificador e reversibilidade | Faixas, classificador em dois estágios, snapshot/`/undo`, aprovação por intenção, modos, blocklist, Inbox, auditoria | [`sprint-2.md`](sprints/sprint-2.md) | 📋 |
| **Sprint 3** | Sessões e daily | `sessions.db`, títulos, daily e virada, threads e `session_branch`, `/resume` por data, migração | [`sprint-3.md`](sprints/sprint-3.md) | 📋 |
| **Sprint 4** | Escrita e core | Core congelado, detector de saliência, Mordomo com evidência ancorada, observações locais, sinais implícitos, fatos com escopo/proveniência/tempo, diretivas, "aprendi · desfazer" | [`sprint-4.md`](sprints/sprint-4.md) | 📋 |
| **Sprint 5** | Consolidação e recall | Cartões, rollups, Reflector, pendências proativas, perfil do Senhor, turnos indexados, PT-BR sem modelo, oferta do modelo multilíngue, `sqlite-vec`, `session_search`, `/memory` editar/esquecer/purge | [`sprint-5.md`](sprints/sprint-5.md) | 📋 |
| **Sprint 6** | Núcleo enxuto e prova | Tools adiadas, cache, R-17, suíte `tests/memory_eval/`, avaliação ao vivo da extração, rodada real | [`sprint-6.md`](sprints/sprint-6.md) | 📋 |

Ordem: 1 → 2 (governança) e 3 → 4 → 5 (memória) são duas trilhas; a 3 pode começar depois da 1. A 6 fecha a versão.

---

## 4. Arquitetura Alvo & Componentes Afetados

```
src/orion/governance/pep.py                 [mod]   faixas, modos novos, escopo do usuário, Inbox sem humano      S1-S2
src/orion/governance/bands.py               [novo]  faixa por reversibilidade + blocklist rígida                  S2
src/orion/governance/classifier.py          [novo]  RiskClassifier: regras + modelo FAST cego ao raciocínio      S2
src/orion/governance/reversibility.py       [novo]  snapshot em ~/.orion/trash, git stash-sombra, /undo           S2
src/orion/governance/grants.py              [novo]  aprovação por intenção com escopo e TTL                        S2
src/orion/governance/nuclear.py             [mod]   polkit/PAM/fprintd; remove "qualquer texto vale"               S1
src/orion/governance/askpass.py             [novo]  helper SUDO_ASKPASS + chaveiro (secretstorage), fora do LLM    S1
src/orion/governance/trust_ledger.py        [mod]   instanciado na sessão; assinatura por prefixo                  S1
src/orion/runtime/tools/run_command.py      [mod]   sudo -A com SUDO_ASKPASS                                       S1
src/orion/runtime/web_policy.py             [mod]   allowlist -> blocklist; sessão contaminada                     S1
src/orion/runtime/search/                   [novo]  SearchProvider: brave, ddgs, searxng                           S1
src/orion/sessions/index.py                 [novo]  sessions.db (FTS5), daily, threads, migração                    S3
src/orion/tui/commands/resume.py            [mod]   seletor com busca por nome e data, árvore                       S3
src/orion/memory/core_block.py              [novo]  bloco core congelado por sessão (substitui manifest.py)        S4
src/orion/memory/salience.py                [novo]  detector de saliência determinístico                           S4
src/orion/memory/steward.py                 [novo]  Mordomo: ops ADD/UPDATE/SUPERSEDE/CONFIRM/NOOP                  S4-S5
src/orion/memory/facts_store.py             [mod]   escopo, proveniência, valid_from/valid_to, PROVISIONAL          S4
src/orion/memory/vector_store.py            [mod]   multilíngue + sqlite-vec                                       S5
src/orion/memory/rollups.py                 [novo]  cartões de sessão e rollups dia/semana/mês/ano                  S5
src/orion/memory/observations.py            [novo]  observações compactas de leituras locais (tool_obs)              S4
src/orion/memory/signals.py                 [novo]  sinais implícitos: PEP, /undo, edição do Senhor, ritmo           S4
src/orion/memory/commitments.py             [novo]  pendências, superfície na daily/workspace, prazo no scheduler   S5
src/orion/memory/profile.py                 [novo]  perfil semanal do Senhor com fontes, dentro do core              S5
src/orion/memory/ptbr.py                    [novo]  stemmer leve PT-BR para FTS5                                     S5
src/orion/core/engine.py                    [mod]   core no system, recall fora do transcript, tools adiadas       S4, S6
src/orion/core/identity.py                  [mod]   preâmbulo enxuto + princípio ADR-027                           S6
```

---

## 5. Matriz de Critérios de Aceite da Versão (DoD Global)

| ID | Cenário | Comportamento Esperado | Como Validar | Status |
|:---|:---|:---|:---|:---|
| CA-01 | Senha do sudo | `sudo apt update` pede a senha uma vez num overlay; o sudo a verifica; senha errada falha como no terminal | teste com PAM falso + manual no GNOME | 📋 |
| CA-02 | Senha lembrada | Com `orion setup sudo`, `sudo apt install x` roda sem pergunta; `sudo dd ...` nunca é preenchido | `tests/unit/test_askpass.py` | 📋 |
| CA-03 | Segredo fora do contexto | A senha não aparece no contexto, na auditoria, nos logs nem no transcript | teste de varredura | 📋 |
| CA-04 | Outro repositório | "Edite o README de ~/outro-repo" funciona sem pergunta no modo `auto` | `tests/e2e/test_security_audit.py` | 📋 |
| CA-05 | Web aberta | `web_fetch` abre domínio público fora da antiga lista; IP privado continua negado; busca cai na reserva sem chave | `tests/unit/test_web_*` | 📋 |
| CA-06 | Reversibilidade | `rm` de 30 arquivos não commitados roda sem pergunta e `/undo` os restaura | `tests/unit/test_reversibility.py` | 📋 |
| CA-07 | Nuclear | `mkfs`, `dd of=/dev/sdX`, push --force na main pedem senha verificada; senha errada nega; blocklist nunca roda, nem em `full` | `test_security_audit.py` | 📋 |
| CA-08 | Sem humano | No daemon, uma ação de presença vira pendência na Inbox, não negação | `tests/unit/test_daemon_*` | 📋 |
| CA-09 | Identidade sem tool | Numa sessão nova, sem `memorize` no turno, o ORION trata o Senhor por "Senhor" e sabe o que foi confirmado antes | `tests/memory_eval/` | 📋 |
| CA-10 | Mordomo | Uma correção ("não, é Postgres 16") vira SUPERSEDE; inferência nasce PROVISÓRIA; CONFIRMADO nunca é sobrescrito por inferência | `tests/memory_eval/` | 📋 |
| CA-11 | Daily | A virada fecha a daily de ontem com cartão; a nova começa com o resumo curto de ontem | `tests/unit/test_daily.py` | 📋 |
| CA-12 | Threads | Na daily, um tópico sustentado abre uma sessão; "volte para a sessão X" retoma | `tests/memory_eval/` | 📋 |
| CA-13 | `/resume` por data | `ontem`, `semana`, `nov`, `2026` e nome filtram; árvore ano › mês › dia | lab | 📋 |
| CA-14 | Pergunta temporal | "O que fizemos semana passada?" responde a partir dos rollups | `tests/memory_eval/` | 📋 |
| CA-15 | Núcleo enxuto | Primeiro turno < 6k tokens de prompt | `tests/unit/test_prompt_budget.py` | 📋 |
| CA-16 | Sem regressão | Suíte padrão e lab passam | `pytest tests/` + `pytest -m lab` | 📋 |
| CA-18 | Sem autoconfirmação | O Mordomo reafirmando um PROVISIONAL sem nova fala do Senhor não o promove; op sem `evidence_refs` válida é descartada | `tests/unit/test_fact_evidence.py` | 📋 |
| CA-19 | Fato de leitura local | Ler `pyproject.toml`/`docker-compose.yml` gera fato `scope=project` com `source=tool`; conteúdo de web/MCP nunca vira fato | `tests/memory_eval/` | 📋 |
| CA-20 | Sinal implícito | Edição do Senhor sobre escrita do agente e negações no PEP viram sinais; com uma fala, viram preferência PROVISÓRIA | `tests/memory_eval/` | 📋 |
| CA-21 | Proatividade | Pendência de ontem aparece na abertura da daily e ao entrar no workspace dela, sem pergunta e sem token extra fora do core | `tests/memory_eval/` | 📋 |
| CA-22 | Perfil | O perfil semanal cabe em 400 tokens, toda frase cita fonte e trecho editado pelo Senhor é preservado | `tests/unit/test_profile.py` | 📋 |
| CA-23 | Detalhe achado | Um detalhe dito numa sessão e ausente do cartão é achado por `session_search` (turnos indexados) | `tests/memory_eval/` | 📋 |
| CA-24 | Purge | `/memory purge` apaga fato, evidências, vetores, FTS e menções no perfil; auditoria sem conteúdo | `tests/unit/test_memory_purge.py` | 📋 |
| CA-25 | Extração ao vivo | 30 diálogos PT-BR: precisão >= 0,90, recall >= 0,80, CONFIRMED indevido = 0, fato de web = 0, custo <= US$ 0,50 | `ORION_LIVE=1 pytest -m live tests/memory_eval/live` | 📋 |
| CA-17 | Rodada real | Sessão real de 1 dia útil com memória, sudo e web | manual, `ORION_LIVE=1`, teto no `BudgetGuard` | 📋 |

---

## 6. Checklist de Conclusão da Spec (Congelamento)

- [x] Pesquisa e diagnóstico registrados (`pesquisa-memoria-e-autonomia.md`).
- [x] ADR-046 a 052 e emendas registrados em `.claudex/decisions.md` (aprovados pelo Senhor ao aprovar o plano em 16/11/2026).
- [x] `system_patterns.md` §1.2 e §3 atualizados.
- [ ] Mudança do `CLAUDE.md` (§2.4) aplicada na Sprint 1.
- [ ] Todos os critérios de aceite validados.
- [ ] Cobertura >= 85%, `ruff` e `mypy` limpos.
- [ ] Um commit por sprint; merge e tag só com confirmação do Senhor.

---

## 7. Riscos e Pendências Conhecidas

| Risco | Mitigação |
|:---|:---|
| Classificador deixa passar ação exagerada (~17% no estudo da Anthropic) | Rede de segurança independente dele: reversibilidade, faixa Nuclear determinística e blocklist |
| Senha no chaveiro lida por outro processo do usuário | Opt-in; o helper só preenche o que o classificador marcou não destrutivo; alternativa sudoers com lista revisada; `orion setup sudo --forget` |
| Injeção de prompt por web aberta | Classificador cego às saídas de tool; sessão contaminada endurece contra exfiltração; conteúdo externo é dado, não instrução |
| Mordomo grava lixo ou alucina | Ops contra vizinhos, PROVISÓRIO por padrão, CONFIRMADO só por Senhor ou repetição, linha "desfazer", fila de revisão; qualidade medida por avaliação ao vivo (CA-25) |
| Mordomo confirma a própria inferência por repetição | Evidência ancorada: toda op cita ids do delta; promoção conta só falas do Senhor em 3 sessões distintas (`fact_evidence`), nunca reafirmação do modelo |
| Perfil vira estereótipo ou inventa | Toda frase cita fonte; sem ref, a frase cai; o perfil nunca vira fato CONFIRMED; o Senhor edita e o trecho dele é preservado |
| Sinais implícitos viram vigilância | Só eventos que o ORION já produz; agregados de horário; nunca saem da máquina além do resumo ao Mordomo; `/memory purge` apaga |
| Proatividade vira ruído | Até 5 pendências, só na abertura da daily e na entrada do workspace, dentro do core; pergunta "ainda vale?" uma única vez aos 30 dias |
| Custo do Mordomo e do classificador | Disparo por saliência e por evento, só o delta, cache por assinatura no ledger, tetos por origem no `BudgetGuard` |
| Snapshot enche o disco | Teto de tamanho e retenção de 7 dias; acima do teto, a ação sobe para Nuclear |
| Migração quebra sessões e fatos antigos | Migração idempotente com backup em `~/.orion/backup/v0.5.2/` antes de tocar nos bancos |
| Modelo multilíngue maior (~220 MB) | Download só por `/memory model install` (ADR-040); BM25 continua funcionando sem ele |
| polkit indisponível (sem agente gráfico) | PAM do usuário com overlay; sem display e sem TTY, Inbox (nunca execução) |
