# Rascunhos de posts (ORION)

> Rascunhos para o Senhor ajustar. Troque `[GIF]`, `[LINK]` e números por dados reais antes de publicar.
> Números do README em 16/11/2026: 2123 testes, 93,6% de cobertura. Confirme na hora de postar.

---

## 1. LinkedIn (PT-BR), build in public, agora

Passei os últimos meses construindo uma coisa que eu queria ter: um agente de engenharia que mora no meu terminal e se comporta como um colega confiável, não como uma caixa-preta.

O ORION (Operational Reasoning & Intelligence Orchestration Network) é open source e tem três ideias fixas:

1. Nega por padrão. Toda ação que muda algo passa por um ponto de política (PEP). Comando destrutivo exige autenticação do sistema operacional, e nenhum hook, subagente ou agendamento consegue contornar isso.
2. Lembra de você. Memória em cinco camadas, com linha do tempo pesquisável, decisões de projeto e preferências, sem mandar nada para fora sem sua permissão.
3. Gasta zero token parado. O daemon opcional agenda e vigia coisas sem chamar o modelo até ser preciso. E mostra o custo de cada turno em reais e dólares.

[GIF: painel [PEP] pedindo aprovação]

Hoje roda em Linux, tem 2.123 testes automatizados e 93% de cobertura. Ainda faltam voz, memória completa e instalação fácil em Mac e Windows. Estou construindo isso em público, uma sprint de cada vez, com especificação antes de código.

Se você usa agentes no terminal, o que mais te incomoda neles hoje: custo, segurança ou perda de contexto?

Repositório: [LINK]

#opensource #AI #agents #terminal #python

---

## 2. X / Twitter (EN), thread

**1/** I've been building O.R.I.O.N: a personal engineering agent that lives in your terminal. Open source, local-first, and it asks before it acts. [GIF]

**2/** Deny by default. Every mutating action goes through a Policy Enforcement Point. Destructive commands need OS-level step-up auth. Hooks, subagents and schedules can't bypass it. [GIF: [PEP] prompt]

**3/** It remembers. Five memory spheres: user profile, identity, environment, typed project decisions, and a searchable episodic timeline (SQLite FTS5 + optional local embeddings). Nothing downloaded without consent.

**4/** Zero tokens when idle. An opt-in daemon runs schedules and jobs without calling a model until something needs reasoning. Every turn shows its real cost in USD/BRL, with a daily budget cap.

**5/** MCP native, subagents with privilege ceilings, skills (SKILL.md), sessions with resume/rewind. 2,100+ tests, 93% coverage, no automated test ever hits a paid provider.

**6/** Linux today. Voice, full memory and Mac/Windows are next. Building in public, spec first. Repo: [LINK]. What would you want an agent like this to do on your machine?

---

## 3. Show HN (para o lançamento maior, não agora)

**Título:** Show HN: ORION – a local-first terminal agent that asks before it acts

**Primeiro comentário (EN):**

Hi HN. I built ORION because I wanted a terminal agent I could leave running without worrying about what it does to my machine or my token bill.

What's different:
- Every mutating action goes through a deny-by-default policy layer; destructive ones require OS step-up auth that nothing in the agent can bypass.
- Memory is more than a vector store: a chronological timeline, typed project decisions, and a user/environment profile.
- An opt-in daemon (systemd --user) runs schedules with zero model calls while idle.
- It's MCP-native, tracks real cost per turn, and falls back to a local model.

What it isn't, yet: it's Linux-first (Mac/Windows in progress), alpha, and voice isn't there. [Honest note on how it was built, optional: most of the code was written with Claude Code under a spec-first workflow, and later the agent was run on its own repo.]

I'd love feedback on the permission model in particular. Repo: [LINK]

---

## 4. Reddit (r/LocalLLaMA ou r/commandline), post técnico

**Título:** How I got my terminal agent to cost $0 while idle (and why deny-by-default matters)

**Corpo:**

I've been building an open-source terminal agent (ORION) and wanted to share two design decisions that turned out to matter:

1. **Idle = zero tokens.** The scheduler/daemon only wakes the model on an event or schedule that needs reasoning. Everything else (cron, watchers, notifications) is plain code. [short explanation + diagram]
2. **A policy layer the model can't talk its way around.** Tool calls get a level from 0 to 3; level 3 needs OS authentication, and hooks/subagents/rules can't lower it. [short explanation]

Repo if you want to look at the code or break the policy layer: [LINK]. Happy to answer questions about the tradeoffs.

> Antes de postar: leia as regras do subreddit e participe de outras threads primeiro.

---

## 5. Bio curta (GitHub / X / LinkedIn)

"Building ORION: an open-source, local-first personal engineering agent for the terminal. Deny by default. Zero tokens when idle."
