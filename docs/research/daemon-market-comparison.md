# Pesquisa — Daemon de agente: comparação de mercado (09/11/2026)

> Fontes majoritariamente de terceiros (blogs, tutoriais, espelhos de README). Confirmar nas docs oficiais antes de tratar como fato.

| Aspecto | Claude Code | Hermes Agent | Antigravity | ORION S7 |
|---|---|---|---|---|
| Processo persistente | Sem daemon único: Routines (nuvem), tarefas agendadas do Desktop, `/loop`, Remote Control, Channels | Gateway único; `hermes gateway install` vira serviço; cron dentro dele | Agent Manager no app Desktop | `systemd --user`, opt-in |
| Agenda | `/loop` em sessão; Desktop persiste entre reinícios | Tick de 60 s, file lock, sessão nova por job | Execuções agendadas (2.0) | SQLite, catch-up, sessão limpa por disparo |
| Aprovação/notificação | Channels, Remote Control | Entrega em Telegram, Discord etc. | Inbox com sino e ponto azul, notificação do SO | Notificação com botões, Telegram com TTL, Inbox |
| Custo em idle | Depende da superfície | Cada disparo chama o agente | Não documentado | Zero (ADR-022), provado em teste |

## Fontes
- Hermes: https://fast.io/resources/hermes-agent-scheduled-automations-cron/ · https://hermes-agent.org/ · https://lumadock.com/tutorials/run-hermes-agent-with-systemd
- Claude Code: https://rickhigh.substack.com/p/claude-code-advanced-the-four-ways · https://the-decoder.com/anthropic-turns-claude-code-into-a-background-worker-with-local-scheduled-tasks/
- Antigravity: https://codelabs.developers.google.com/getting-started-google-antigravity · https://arjankc.com.np/blog/google-antigravity-agent-manager-explained
- OpenClaw (serviço por SO): https://docs.openclaw.ai/cli/daemon
- Wayland sem layer-shell no GNOME: https://gitlab.freedesktop.org/wayland/wayland/-/issues/305
- Ações em notificações: https://python-sdbus-notifications.readthedocs.io/en/stable/
