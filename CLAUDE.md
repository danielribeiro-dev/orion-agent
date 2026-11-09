# CLAUDE.md — O.R.I.O.N (orion-agent)

Agente pessoal de engenharia no terminal (Python 3.11+). Visão: um "Jarvis" sempre presente, soberano e econômico em tokens. Trate o usuário por "Senhor". Docs internos em PT-BR; README público em inglês.

## Ler antes de qualquer sprint
1. `.claudex/active_context.md` (estado atual e próximo passo)
2. `docs/planning/versions/<versão ativa>/VERSION.md` e `sprints/sprint-N.md`
3. `.claudex/decisions.md` (ADRs) e `.claudex/system_patterns.md` (invariantes)

## Regras
- **Doc-First:** nenhuma linha em `src/` sem comando explícito de início da sprint e spec congelada. Cada sprint roda em sessão própria.
- **Segurança:** toda ação mutante passa pelo PEP (`governance/pep.py`); deny by default; ações nucleares exigem step-up do SO e nunca são contornáveis (hooks, subagents, agendamentos ou regras). Tool nova precisa de nível PEP definido.
- **Brain/Body:** `orion.core` não faz I/O direto. Runtime e dados somente em `~/.orion/`, nunca no repositório. Segredos nunca em arquivos versionados.
- **Qualidade:** `ruff check`, `mypy` strict, cobertura global ≥ 85%, SQL sempre parametrizado, `asyncio` em tudo.
- **TUI:** sem emojis; glifos permitidos `❯ ● ✔ ✖ ! [PEP] › · │` (`docs/design/CLI_AGENT_RULES.md`). Novo slash command: classe em `src/orion/tui/commands/` + registro em `tui/completer.py`.
- **Custos reais:** nenhuma chamada paga a provedor roda em teste automático; use opt-in `ORION_LIVE=1` e respeite o teto de `BudgetGuard`.
- **Merge em `main`, tags e push** só com confirmação explícita do Senhor.

## Fluxo de sprint
Escopo (do `sprint-N.md`) → implementar → testes → `ruff`/`mypy`/`pytest --cov=src/orion` → atualizar `.claudex/progress.md`, `active_context.md` e a tabela do `VERSION.md` → um commit `feat(<escopo>): vX.Y.Z Sprint N — <título>` (Conventional Commits; escopos: `mcp`, `tui`, `gateway`, `governance`, `context`, `docs`...).

## Comandos
```bash
pip install -e ".[dev]"
pytest tests/ --cov=src/orion --cov-report=term-missing   # ~20 s
pytest tests/e2e/test_security_audit.py -v
ruff check src tests && mypy src
orion-agent            # CLI interativa; `orion` é alias da mesma CLI (ADR-033 emenda o ADR-014 v0.4.0); o desktop será um app instalável, não iniciado por terminal
orion-agent daemon status|start|stop|enable [--boot]|disable   # daemon opt-in (systemd --user); `daemon run` é o que a unit executa
orion-agent attach     # anexa o terminal ao daemon (Inbox, eventos, prompts)
```

## Mapa rápido de `src/orion/`
`core/` engine ReAct, FSM, eventos · `agents/` subagents (runner, orçamento, definições, portas) · `gateway/` providers, router, ledger, circuit breaker · `runtime/` tools e provider local · `governance/` PEP, auditoria, trust ledger, nuclear · `memory/` timeline, vetores, fatos, manifesto · `timeline/` compactor e branches · `skills/` · `mcp/` cliente MCP · `daemon/` IPC, servidor, boot/pressão, jobs, systemd · `scheduler/` cron e agenda · `notify/` Inbox, desktop, Telegram, roteador · `presence/` política de presença da memória · `tui/` sessão, sink, attach, prompt, renderer, comandos.

## Estado
v0.4.0 implementada; v0.5.0 "Claude-Grade Agent" em execução (ver `active_context.md`); Sprint 7 (daemon) implementada, validação manual no GNOME pendente. Daemon é opt-in e nunca liga sem ação explícita do Senhor. Numeração de ADRs duplicada entre versões é desambiguada por sufixo `[vX.Y.Z]`.
