# CLAUDE.md — O.R.I.O.N (orion-agent)

Agente pessoal de engenharia no terminal (Python 3.11+). Visão: um "Jarvis" sempre presente, soberano e econômico em tokens. Trate o usuário por "Senhor". Docs internos em PT-BR; README público em inglês.

## Ler antes de qualquer sprint
1. `.claudex/active_context.md` (estado atual e próximo passo)
2. `docs/planning/versions/<versão ativa>/VERSION.md` e `sprints/sprint-N.md`
3. `.claudex/decisions.md` (ADRs) e `.claudex/system_patterns.md` (invariantes)

## Regras
- **Doc-First:** nenhuma linha em `src/` sem comando explícito de início da sprint e spec congelada. Cada sprint roda em sessão própria.
- **Segurança:** toda ação mutante passa pelo PEP (`governance/pep.py`), que decide por raio de destruição e reversibilidade (ADR-046); escopo = espaço do usuário, não o cwd. Ações nucleares exigem presença verificada (polkit/PAM, ADR-048) e nunca são contornáveis (hooks, subagents, agendamentos, regras ou modo `full`). Tool nova precisa de faixa PEP definida. A senha do SO nunca entra no contexto do modelo.
- **Brain/Body:** `orion.core` não faz I/O direto. Runtime e dados somente em `~/.orion/`, nunca no repositório. Segredos nunca em arquivos versionados: chaves em `~/.orion/.env` (0600, ADR-042), que o agente não lê nem altera.
- **Qualidade:** `ruff check`, `mypy` strict, cobertura global ≥ 85%, SQL sempre parametrizado, `asyncio` em tudo.
- **TUI:** sem emojis; glifos permitidos `❯ ● ✔ ✖ ! [PEP] › · │` (`docs/design/CLI_AGENT_RULES.md`). Novo slash command: classe em `src/orion/tui/commands/` + registro em `tui/completer.py`.
- **Custos reais:** nenhuma chamada paga a provedor roda em teste automático; use opt-in `ORION_LIVE=1` e respeite o teto de `BudgetGuard`.
- **Merge em `main`, tags e push** só com confirmação explícita do Senhor.

## Testes e avaliação da TUI
Guia completo em `.claudex/tooling.md` (ler antes de testar ou mexer na TUI). Resumo:
- Testes: `export PATH="$PWD/.venv/bin:$PATH"` e depois os comandos da seção Comandos. Sem CI e sem `ORION_HOME`: isole `HOME`/`tmp_path` para não tocar o `~/.orion` real.
- Dois MCPs de TUI instalados (escopo de usuário): **`tui-mcp`** para olhar (PNG com cor, leia com `Read`) e **`ptywright`** para regredir (asserções, cor por célula, goldens). Abrir o ORION com HOME temporário, esperar `❯` (partida de 7 a 16 s) e nunca enviar prompt livre ao modelo sem `ORION_LIVE=1`.
- Mudanças de interface seguem o ciclo capturar → comparar com a referência → mapear arquivo em `tui/` → corrigir em sprint → recapturar.
- Harness `tests/lab/` (ADR-041): `pytest -m lab tests/lab` (~6 min, opt-in); `open_lab(..., fullscreen=True)` e `tests/lab/launcher.py --fullscreen` abrem a tela cheia com o provider roteirizado (custo zero).

## Fluxo de sprint
Escopo (do `sprint-N.md`) → implementar → testes → `ruff`/`mypy`/`pytest --cov=src/orion` → atualizar `.claudex/progress.md`, `active_context.md` e a tabela do `VERSION.md` → um commit `feat(<escopo>): vX.Y.Z Sprint N — <título>` (Conventional Commits; escopos: `mcp`, `tui`, `gateway`, `governance`, `context`, `docs`...).

## Comandos
```bash
pip install -e ".[dev]"
scripts/install.sh [--dev]   # `orion` em ~/.local/bin sem venv (ADR-044); `orion update [--check|--rollback]`
pytest tests/ --cov=src/orion --cov-report=term-missing   # ~20 s
pytest tests/e2e/test_security_audit.py -v
ruff check src tests && mypy src
orion-agent            # CLI interativa em tela cheia (ADR-043; ORION_TUI=classic ou /tui classic para o modo antigo); `orion` é alias da mesma CLI (ADR-033 emenda o ADR-014 v0.4.0); o desktop será um app instalável, não iniciado por terminal
orion-agent daemon status|start|stop|enable [--boot]|disable   # daemon opt-in (systemd --user); `daemon run` é o que a unit executa
orion-agent attach     # anexa o terminal ao daemon (Inbox, eventos, prompts)
```

## Mapa rápido de `src/orion/`
`core/` engine ReAct, FSM, eventos · `agents/` subagents (runner, orçamento, definições, portas) · `gateway/` providers, router, ledger, circuit breaker · `runtime/` tools e provider local · `governance/` PEP, auditoria, trust ledger, nuclear · `memory/` timeline, vetores, fatos, manifesto · `timeline/` compactor e branches · `skills/` · `mcp/` cliente MCP · `daemon/` IPC, servidor, boot/pressão, jobs, systemd · `scheduler/` cron e agenda · `notify/` Inbox, desktop, Telegram, roteador · `presence/` política de presença da memória · `tui/` sessão, sink, attach, prompt, renderer, comandos; `tui/screen/` tela cheia (transcrição em células, app, modo, sinais do terminal) · `install.py` instalação, update e rollback.

## Estado
v0.4.0 implementada; v0.5.0 "Claude-Grade Agent" em execução (ver `active_context.md`); Sprint 7 (daemon) implementada, validação manual no GNOME pendente; v0.5.1 "Horizon" (TUI): Sprints 1 e 2 implementadas; v0.5.2 "Bridge" (tela cheia, movimento, memória legível, instalação sem venv): Sprints 0 a 4 implementadas (`docs/planning/versions/v0.5.2/`); falta a rodada com modelo real das duas. v0.5.3 "Memória Viva e Núcleo Livre" (governança por reversibilidade, senha verificada, web aberta, Mordomo da Memória, daily e threads): Sprint 0 (spec, com emenda da memória) e Sprint 1 (liberdade básica) concluídas, Sprints 2 a 6 aguardam comando (`docs/planning/versions/v0.5.3/`). Daemon é opt-in e nunca liga sem ação explícita do Senhor. Numeração de ADRs duplicada entre versões é desambiguada por sufixo `[vX.Y.Z]`.
