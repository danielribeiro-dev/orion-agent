# Sprint — v0.5.0 Sprint 7: Daemon, Jobs & Schedules

> **Status:** ✅ Implementada em 09/11/2026 (7A + 7B + 7C; validação manual no GNOME pendente)  
> **Versão Relacionada:** v0.5.0  
> **Responsável / Agente:** Daniel Dev & Claude (via ORION)  
> **Data de Início:** 09/11/2026  
> **Data de Conclusão:** 09/11/2026 (código e testes; ver §8.1)  
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
- [x] **7A — Boot e pressão (ADR-035):** sondagem de hardware (RAM, núcleos, carga, PSI, bateria/tomada, disco) e perfil `auto|minimal|full` (`daemon.boot_profile`); espera por estabilização com teto; componentes carregados sob demanda; `PressureMonitor` puro (sem LLM) com histerese que dorme/acorda componentes via porta `Sleepable`; limites de systemd (`Nice`, `CPUWeight`, `IOWeight`, `MemoryHigh`).
- [x] **7A — Fundação:** `SessionSink` (`RichSink`/`IpcSink`), `daemon/` (asyncio, JSON-RPC em socket Unix 0600, `SO_PEERCRED`), `attach`/detach com reconexão, `DaemonSettings`, `/daemon`, `install/enable/disable`, tool `daemon_control`.
- [x] **7B — Agenda e jobs:** `scheduler/` e tools `schedule_create/list/delete`; catch-up (`skip|run_once`); jobs supervisionados (Headroom Guard) e logs; `origin=cron|daemon`; teto de custo por origem; triagem barata antes de acordar o modelo.
- [x] **7C — Notificação e HITL:** `notify/` (desktop com ações, Telegram), Inbox, roteador de saída, canal de pensamentos opt-in (`ui.show_thinking`), medição de idle.
- [x] **7C — Presença guiada por memória (ADR-036):** `PresencePolicy` determinística que lê regras de `facts.db` (janelas de silêncio, rebaixar canal, resumo agrupado, exceções críticas); criação de regras e schedules por conversa, com confirmação; registro de sinais de feedback (dispensada, ignorada, aprovada) para a memória viva (ADR-027).
- [x] Documentar aba flutuante e voz (`docs/planning/vision/ambient-panel-and-voice.md`).

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
- [x] mypy/ruff limpos; cobertura ≥ 85%; `.claudex/progress.md`, `active_context.md` e `VERSION.md` atualizados.

## 8.1 Registro de implementação (2026-11-09)

**Commits:** `d89f1d8` (SessionSink, em commit próprio) e o commit `feat(daemon)` da sprint. Módulos-folha (`scheduler/`, `notify/`, `presence/`, `daemon/{probe,pressure,sleepable,service}`) foram escritos por subagents em paralelo sobre contratos fixados antes (`notify/models.py`, `settings/models.py`) e revisados na integração.

**Entregue**
* **7A:** `tui/sink.py` (`RichSink` = `StreamRenderer`, `IpcSink`, `NullSink`, `apply_sink_event` com lista fechada de métodos); `AgentSession` aceita `status_bar`/`console`/`sink` opcionais e `origin`; headless sem asker deixa o PEP não interativo (nuclear negado). `daemon/ipc.py` (JSON-RPC 2.0 por linha, socket `0600` em diretório `0700` sob `$XDG_RUNTIME_DIR/orion`, `SO_PEERCRED`, erro claro para caminho acima de 107 bytes), `server.py` (fila limitada por assinante, publish thread-safe), `client.py` (`follow` com reconexão e backoff), `app.py` (`OrionDaemon`), `control.py`, `service.py` (unit com `Nice`/`CPUWeight`/`IOWeight`/`MemoryHigh`, validada por `systemd-analyze --user verify`), `probe.py`, `pressure.py`, `sleepable.py`. CLI: `orion-agent daemon run|start|stop|restart|status|install|enable [--boot]|disable` e `orion-agent attach`; `orion` agora aponta para `orion.cli:main` (ADR-033). `/daemon` (catálogo 29 -> 30) e tool `daemon_control`.
* **7B:** `scheduler/{cronspec,store,runner}.py` (cron de 5 campos com regra Vixie, macros, intervalos >= 60 s, one-shot ISO; SQLite `schedules.db` 0600; `SchedulerLock` por `flock`; catch-up `skip|run_once`); `daemon/jobs.py` (Headroom Guard, teto de concorrência, `nice`, teto de saída, log 0600, linhas viram `job.output`); tools `schedule_create|list|delete`; `BudgetGuard.origin_budget_usd` com `OriginBudgetExceededError` (subclasse do erro global, então runner e sessão já o tratam); `daemon.origin_budget_usd` padrão `cron 0.50`, `daemon 0.25`, `loop 1.00`.
* **7C:** `notify/{inbox,desktop,telegram,router}.py` (`notify-send --action --wait`; Telegram por Bot API com callback só do dono, TTL e token redigido dos logs; Inbox com resolução única, expiração, resumo segurado e log de feedback); `presence/{rules,policy,activity}.py`; tools `presence_rule_create|list|delete`; `ui.show_thinking` controla o canal de pensamentos do `IpcSink`; medidor `OrionDaemon.provider_calls`.

**Desvios e decisões de implementação**
* **Níveis PEP:** `daemon_control`, `schedule_create`, `schedule_delete`, `presence_rule_create` e `presence_rule_delete` são LEVEL_3 (o LEVEL_2 é aprovado sozinho em `WORKSPACE_AUTO`, o que violaria "sempre com confirmação"). `schedule_list`/`presence_rule_list` são LEVEL_0. Todas em `FORBIDDEN_FOR_CHILD`.
* **Disparo agendado:** sessão limpa por disparo, headless, `origin=cron`, PEP não interativo e modo `min(sessão, agendamento)`. Em `SUPERVISED` (padrão) o disparo só lê; mutar exige o Senhor ter agendado com autonomia maior e ela não passar da configurada. Comando nuclear agendado é negado mesmo em `FULLY_AUTO` (teste com canário).
* **Triagem:** a do agendamento é a determinística por git (custo zero). Como ela pularia tarefas que não dependem do repositório (briefing, lembrete), a tool cria com `triage=false` por padrão; o modelo da `Schedule` mantém `True` como no contrato.
* **`daemon` só da camada do usuário:** projeto e local nunca ligam nem configuram o daemon (mesmo confiáveis); `ui` mescla normalmente. Disparo em projeto não confiável é negado; as tools recusam criar agenda ou controlar o daemon nele.
* **`daemon run` exige opt-in:** recusa sem `daemon.enabled` (só `--force` em primeiro plano). `start` marca o opt-in sem autostart; `enable` sobe no login; `--boot` liga o linger e grava marcador, e `disable` só desfaz o linger que o ORION ligou.
* **Perfil e componentes:** a sessão do daemon é componente `high` carregado sob demanda e fica fora do perfil `minimal` (o `prompt` do attach responde negado com a explicação). A espera por estabilização roda depois do IPC subir, para `status` responder durante a espera.
* **Attach:** cliente leve (prompt_toolkit + `RichSink` local reaplicando eventos), não a TUI completa; os comandos do attach são `/inbox`, `/approve`, `/deny`, `/status`, `/detach`. Aprovação nuclear nunca é remota (o roteador recusa e o PEP do disparo nunca pergunta).
* **Briefing com modelo:** é um agendamento comum (`schedule_create`), sob o teto de `cron`; a regra `briefing` só define quando entregar o resumo agrupado.
* **Hooks:** `DaemonStart`/`DaemonStop` (só da camada do usuário) e `ScheduleFire` (na sessão do disparo).
* **Smoke real isolado** (`HOME` e `XDG_RUNTIME_DIR` temporários): socket 0600, perfil `standard` nesta máquina, 0 chamadas ao provider, `shutdown` pelo IPC remove o socket.

**Pendente (exige o Senhor):** teste manual no GNOME (`/daemon enable`, logout/login, agendamento dispara, botão da notificação aprova, `attach` mostra a Inbox); Telegram real (token em `~/.orion/secrets/telegram_token` 0600 e `daemon.notifications.telegram_chat_id`); calibrar limiares de pressão por medição.

---

## 9. Critérios de Parada

1. Qualquer ação agendada executando nível nuclear sem step-up.
2. Chamada ao provider detectada em idle.
3. Daemon ativado sem ação explícita do Senhor.
4. Monitor de pressão acionando LLM ou dormindo componente essencial.
5. Política de presença decidida por código fixo em vez de regra da memória.
