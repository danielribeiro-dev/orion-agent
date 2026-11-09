# Sprint — v0.5.0 Sprint 7: Daemon, Jobs & Schedules

> **Status:** 🧊 Spec congelada em 09/11/2026 (aguarda comando de início, sessão própria)  
> **Versão Relacionada:** v0.5.0  
> **Responsável / Agente:** Daniel Dev & Claude (via ORION)  
> **Data de Início:** —  
> **Data de Conclusão:** —  
> **ADRs:** 022, 032, 033, 034, 035, 036 · **Pesquisa:** `docs/research/daemon-market-comparison.md`

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Um processo de usuário **opt-in** que mantém a sessão viva, agenda tarefas, supervisiona scripts e notifica o Senhor mesmo sem terminal e sem áudio, sem consumir tokens em idle.
* **Dependências Prévias:** Sprints 3, 5, 6.
* **Entregável Verificável:** `/daemon enable`, `orion-agent attach`, tarefa agendada executa após reinício, 1 h de idle com 0 chamadas ao provider, `/daemon disable` reverte tudo.

---

## 2. Contexto de Engenharia

* **Por que existe:** não há daemon, scheduler, jobs em segundo plano nem IPC; o ADR-003 prevê `systemd --user` com TUI sob demanda.
* **Visão:** o daemon é o corpo permanente; a sessão é o cérebro. Superfícies (TUI `attach`, notificação, Telegram, futuramente aba flutuante e voz) são clientes do mesmo IPC.
* **Decisões:** ADR-022 (zero token em idle), ADR-032 (daemon opt-in, IPC, roteador de saída), ADR-033 (`orion` = `orion-agent`), ADR-034 (aba e voz como clientes), ADR-035 (boot escalonado e dormência por pressão), ADR-036 (política de presença guiada por memória).

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Antes | Depois |
| :--- | :--- | :--- |
| **Processo** | Vive e morre com a TUI | Daemon opt-in; TUI é cliente (`attach`/detach) |
| **Autostart** | Inexistente | `install` / `enable` (login) / `enable --boot` (linger explícito); desligado por padrão |
| **Controle** | — | `/daemon ...` e tool `daemon_control` (conversa), sempre com confirmação do PEP |
| **Agendamento** | `/loop` em memória | cron/intervalo/one-shot em `~/.orion/schedules.db`, catch-up após reinício |
| **Jobs** | Só threads internas | Scripts supervisionados com limites e logs; stdout vira evento |
| **Notificação** | Telegram mock | Desktop com botões de ação, Telegram real com TTL, Inbox de pendências |
| **Arranque** | Tudo carrega de uma vez | Perfil `minimal/standard/full` por sondagem de hardware; espera a máquina estabilizar |
| **Pressão do sistema** | Ignorada | Monitor sem LLM põe componentes não essenciais em dormência e os reativa por histerese |
| **Preferências** | Fixas em código | Política de presença lida da memória (silêncio, resumos, canais) |

---

## 4. Escopo da Sprint

### ✅ No Escopo
- [ ] **7A — Boot e pressão (ADR-035):** sondagem de hardware (RAM, núcleos, carga, PSI, bateria/tomada, disco) e perfil `auto|minimal|full` (`daemon.boot_profile`); espera por estabilização com teto; componentes carregados sob demanda; `PressureMonitor` puro (sem LLM) com histerese que dorme/acorda componentes via porta `Sleepable`; limites de systemd (`Nice`, `CPUWeight`, `IOWeight`, `MemoryHigh`).
- [ ] **7A — Fundação:** `SessionSink` (`RichSink`/`IpcSink`), `daemon/` (asyncio, JSON-RPC em socket Unix 0600, `SO_PEERCRED`), `attach`/detach com reconexão, `DaemonSettings`, `/daemon`, `install/enable/disable`, tool `daemon_control`.
- [ ] **7B — Agenda e jobs:** `scheduler/` e tools `schedule_create/list/delete`; catch-up (`skip|run_once`); jobs supervisionados (Headroom Guard) e logs; `origin=cron|daemon`; teto de custo por origem; triagem barata antes de acordar o modelo.
- [ ] **7C — Notificação e HITL:** `notify/` (desktop com ações, Telegram), Inbox, roteador de saída, canal de pensamentos opt-in (`ui.show_thinking`), medição de idle.
- [ ] **7C — Presença guiada por memória (ADR-036):** `PresencePolicy` determinística que lê regras de `facts.db` (janelas de silêncio, rebaixar canal, resumo agrupado, exceções críticas); criação de regras e schedules por conversa, com confirmação; registro de sinais de feedback (dispensada, ignorada, aprovada) para a memória viva (ADR-027).
- [ ] Documentar aba flutuante e voz (`docs/planning/vision/ambient-panel-and-voice.md`).

### 🚫 Fora de Escopo
- Aba flutuante gráfica, voz, wake word, STT/TTS (v0.6.0/v0.7.0). O GNOME/Wayland não oferece layer-shell nem janela "sempre no topo".
- Aprovação **nuclear** remota: continua negada sem step-up local.

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/daemon/{server,ipc,client,service}.py   [novo]
src/orion/daemon/{probe,pressure,sleepable}.py    [novo] sondagem, monitor de pressão, porta Sleepable
src/orion/presence/{policy,rules}.py              [novo] política de presença (lê memória)
src/orion/scheduler/{store,runner,cronspec}.py    [novo]
src/orion/notify/{desktop,telegram,router}.py     [novo]
src/orion/tui/commands/daemon.py                  [novo] + registro em tui/completer.py
src/orion/runtime/tools/{daemon_control,schedule}.py [novo] (níveis PEP definidos)
src/orion/tui/session.py                          [mod] SessionSink, status_bar/console opcionais, origin
src/orion/settings/{models,loader}.py             [mod] DaemonSettings, UiSettings, HOOK_EVENTS
src/orion/gateway/{budget,ledger}.py, cli.py      [mod] teto por origem, subcomandos
packaging/systemd/orion-daemon.service            [novo]
tests/unit/test_daemon.py test_scheduler.py test_notify.py
```

Reuso: `agents/ports.py` (`ExecutorPort`, `TaskStorePort`, `NotifierPort`, `TriagePort`), `agents/loops.py` (`parse_interval`, triagens), `agents/tasks.py` (`recover()`), `AgentEventEnvelope`, `ledger.spent_by_origin()`, `memory/hitl_telegram.py`, `PepAsker`.

---

## 6. Contratos de Código & Tipagem

```python
class Schedule(BaseModel):
    id: str
    spec: str                      # cron | intervalo | ISO datetime
    prompt: str
    autonomy: AutonomyMode         # nunca acima do configurado; nuclear exige step-up
    triage: bool = True            # tenta resolver sem acordar o modelo principal
    catchup: Literal["skip", "run_once"] = "skip"

class DaemonSettings(BaseModel):
    enabled: bool = False          # opt-in
    autostart: Literal["off", "login", "boot"] = "off"
    notifications: NotifySettings  # desktop, telegram
    boot_profile: Literal["auto", "minimal", "full"] = "auto"

class Sleepable(Protocol):
    name: str
    essential: bool                # scheduler, IPC e auditoria nunca dormem
    cost: Literal["low", "medium", "high"]
    async def sleep(self) -> None: ...
    async def wake(self) -> None: ...

class PresenceRule(BaseModel):     # derivada de fatos da memória, confirmada pelo Senhor
    kind: Literal["quiet_window", "digest", "channel_cap", "briefing"]
    window: str                    # relativa ("primeira atividade do dia") ou horária
    channel_cap: Literal["none", "inbox", "notify", "voice"] = "inbox"
    allow_critical: bool = True
class UiSettings(BaseModel):
    show_thinking: bool = False
    panel: bool = False
```

---

## 7. Estratégia de Implementação

1. 7A: extrair `SessionSink` em commit próprio (maior risco de regressão), depois daemon, IPC e autenticação por credenciais do peer.
2. 7A: `attach` reaproveitando a TUI; `/daemon` e `daemon_control`.
3. 7B: scheduler persistente, file lock, retomada e catch-up.
4. 7B: jobs, `origin`, teto por origem.
5. 7C: notificações, HITL remoto, Inbox, medição de idle e custo por origem.

---

## 8. Testes & Critérios de Aceite (DoD)

- Reconexão de cliente; schedule sobrevive a reinício; prova de 0 chamadas ao provider em idle (relógio injetado, 1 h); socket recusa outro usuário.
- Boot: máquina simulada com pouca RAM sobe em `minimal`; forte sobe em `full`; espera de estabilização respeita o teto.
- Pressão: subida de carga causada por processo externo coloca componentes não essenciais em dormência; carga do próprio ORION é descontada; histerese impede oscilação; componentes essenciais nunca dormem; tudo sem chamada ao provider.
- Presença: com regra de manhã silenciosa, nenhuma voz nem notificação sonora é emitida na janela e o conteúdo vira resumo; só crítico fura; sem regra, comportamento padrão.
- Unit gerada válida (`systemd-analyze --user verify`); `disable` remove autostart.
- Segurança: agendado nuclear sem step-up é negado; projeto não confiável não liga daemon nem cria schedules.
- Manual no GNOME: `/daemon enable`, logout/login, schedule dispara, notificação com botão aprova, `attach` mostra Inbox.
- [ ] mypy/ruff limpos; cobertura ≥ 85%; `.claudex/progress.md`, `active_context.md` e `VERSION.md` atualizados.

---

## 9. Critérios de Parada

1. Qualquer ação agendada executando nível nuclear sem step-up.
2. Chamada ao provider detectada em idle.
3. Daemon ativado sem ação explícita do Senhor.
4. Monitor de pressão acionando LLM ou dormindo componente essencial.
5. Política de presença decidida por código fixo em vez de regra da memória.
