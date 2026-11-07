# Sprint — v0.5.0 Sprint 7: Daemon, Jobs & Schedules

> **Status:** 📋 Planejando  
> **Versão Relacionada:** v0.5.0  
> **Responsável / Agente:** Daniel Dev & Claude (via ORION)  
> **Data de Início:** —  
> **Data de Conclusão:** —  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Um processo de usuário que acorda com o PC, mantém a sessão principal viva, agenda tarefas, supervisiona scripts e notifica, sem consumir tokens em idle.
* **Dependências Prévias:** Sprints 3, 5, 6.
* **Entregável Verificável:** `orion daemon install`, `orion attach`, tarefa agendada executa após reinício, 1 h de idle com 0 chamadas ao provider.

---

## 2. Contexto de Engenharia

* **Por que existe:** não há daemon, scheduler, jobs em segundo plano nem IPC; o ADR-003 prevê daemon `systemd --user` com TUI sob demanda.
* **Decisões:** ADR-022 (event-driven, zero token em idle).

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Antes | Depois |
| :--- | :--- | :--- |
| **Processo** | Vive e morre com a TUI | Daemon persistente; TUI é cliente (`attach`/detach) |
| **Agendamento** | Nenhum | cron/intervalo/one-shot em `~/.orion/schedules.db`, `/loop` dinâmico |
| **Jobs** | Só threads internas | Scripts supervisionados com logs; stdout vira evento |
| **Notificação** | Telegram mock | `notify-send` e Telegram real, HITL remoto com TTL |

---

## 4. Escopo da Sprint

### ✅ No Escopo
- [ ] `daemon/` (asyncio + IPC JSON-RPC em socket Unix 0600) e unit `systemd --user`.
- [ ] CLI: `orion daemon start|stop|status|install`, `orion attach`.
- [ ] `scheduler/` e tools `schedule_create/list/delete`.
- [ ] Jobs supervisionados com limites (Headroom Guard) e logs.
- [ ] `notify/` (desktop, Telegram).
- [ ] Triagem barata (Haiku, `max_tokens` mínimo) antes de acordar o modelo principal; ledger por origem (`daemon/cron/loop`).

### 🚫 Fora de Escopo
- Voz, wake word, STT/TTS (v0.6.0).

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/daemon/{server,ipc,client}.py   [novo]
src/orion/scheduler/{store,runner}.py     [novo]
src/orion/notify/{desktop,telegram}.py    [novo]
src/orion/cli.py, gateway/ledger.py       [mod]
packaging/systemd/orion-daemon.service    [novo]
tests/unit/test_daemon.py test_scheduler.py
```

---

## 6. Contratos de Código & Tipagem

```python
class Schedule(BaseModel):
    id: str
    spec: str                      # cron | intervalo | ISO datetime
    prompt: str
    autonomy: AutonomyMode         # nunca acima do configurado; nuclear exige step-up
    triage: bool = True            # tenta resolver sem acordar o modelo principal
```

---

## 7. Estratégia de Implementação

1. Daemon e IPC com autenticação por credenciais do peer.
2. Cliente `attach` reaproveitando a TUI.
3. Scheduler persistente e retomada após reinício.
4. Jobs, notificações e HITL remoto.
5. Medição de idle e custo por origem.

---

## 8. Testes & Critérios de Aceite (DoD)

- Reconexão de cliente; schedule sobrevive a reinício; prova de 0 chamadas ao provider em idle; socket recusa outro usuário.
- [ ] mypy/ruff limpos; cobertura ≥ 85%; `.claudex/progress.md` atualizado.

---

## 9. Critérios de Parada

1. Qualquer ação agendada executando nível nuclear sem step-up.
2. Chamada ao provider detectada em idle.
