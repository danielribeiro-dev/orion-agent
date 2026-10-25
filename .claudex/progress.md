# O.R.I.O.N — Progress & Backlog Tracker
*(Operational Reasoning & Intelligence Orchestration Network)*

## 📊 Status Global do Projeto
- **Repositório:** `orion-agent`
- **Fase Atual:** Fase 1 (v0.1.0) Em Andamento — Sprints 1, 2 e 3 Concluídas | Especificações das Fases 1, 2, 3 e 4 Formalizadas
- **Linhas de Código em `src/`:** ~950 linhas de produção testadas
- **Testes:** 168/168 passando (100% sucesso) · Cobertura: **> 95%** (meta: $\ge 85\%$)

---

## 🗺️ Roadmap de Fases & Sprints

### [CONCLUÍDO] Fase 0: Fundação Documental, Pesquisa de Mercado & Specs da v0.1.0
- [x] Inicialização do repositório Git local e configuração limpa
- [x] Configuração da licença Apache 2.0 e .gitignore
- [x] Estrutura da memória de engenharia em `.claudex/` (`active_context.md`, `progress.md`, `system_patterns.md`, `decisions.md`)
- [x] Especificações Técnicas de Arquitetura em `docs/architecture/`
  - [x] `CORE_REACT_ENGINE.md` (Action-Observation Event Stream, Turn Budgeting, Delimitadores e Artefatos)
  - [x] `TRIPLE_MEMORY.md` (Linha do tempo FTS5, ONNX/FastEmbed local e fatos estruturados)
  - [x] `TIMELINE_SYSTEM.md` (Main Timeline, branches contextuais e síntese de checkpoints)
  - [x] `AMBIENT_VOICE.md` (Daemon headless, Wake Word, Faster-Whisper, Piper e Tone-Mirroring)
  - [x] `MCP_AND_CHANNELS.md` (Cliente MCP, Telegram, WhatsApp e webhooks HTTP)
  - [x] `GOVERNANCE_PEP.md` (Policy Enforcement Point, Permissões LEVEL_0 a LEVEL_3, Auditoria)
  - [x] `MODEL_GATEWAY_COSTS.md` (Multi-provedores, OpenRouter, Auto-Routing por Complexidade e Ledger no CLI)
- [x] Especificações de Superpoderes Modernizados em `docs/specs/superpowers/`
  - [x] `01_SPATIAL_INTERACTION_AND_VISION.md` (MediaPipe ONNX, Ray Casting, AT-SPI2 e Qwen2.5-VL)
  - [x] `02_GHOST_INPUT_AND_CDP.md` (CDP background, uinput Virtual HID e Write-Where-Pointed)
  - [x] `03_AUTONOMOUS_WEB_AND_VAULT.md` (Browser MCP, Zero-Knowledge Keyring e Biometria Vocal)
  - [x] `04_SELF_HEALING_AND_SANDBOX.md` (Tree-sitter multi-linguagem, Bubblewrap Sandbox e Auto-Cura)
  - [x] `05_IMMORTAL_OFFLINE_RESILIENCE.md` (Heartbeat, fallback local, Event Sourcing e reconciliação)
  - [x] `06_WORKFLOW_PROACTIVITY.md` (DBus hooks sem CPU, Git Guard, Protocolo Babá e Morning Summary)
- [x] Design System e Identidade Visual em `docs/design/` (`ASCII_ART_IDENTITY.md`, `TUI_DESIGN_SYSTEM.md`)
- [x] Roadmap Estratégico Master em `docs/planning/ROADMAP.md` (Benchmark Claude Code, Antigravity, OpenHands, Aider)
- [x] Fechamento e congelamento do pacote de especificações da **v0.1.0** em `docs/planning/versions/v0.1.0/`:
  - [x] `VERSION.md`
  - [x] `sprints/sprint-1.md` (Tooling, Tipagem & Skeleton)
  - [x] `sprints/sprint-2.md` (Core ReAct Engine, Action-Observation EventBus & Artefatos)
  - [x] `sprints/sprint-3.md` (As 5 Ferramentas Primitivas Nativas & PEP Determinístico)
  - [x] `sprints/sprint-4.md` (Testes E2E, Cobertura $\ge 85\%$ & Release)
- [x] `README.md` master e plano mestre de engenharia aprovado

---

### [EM PROGRESSO] Fase 1: v0.1.0 Clean Foundation & Core ReAct Engine
- [x] **Sprint 1: Tooling, Tipagem & Skeleton** ✅ CONCLUÍDA (2026-10-24) — Cobertura: 97.48%
  - [x] `pyproject.toml` moderno com PEP 621, hatchling, deps e dev-deps
  - [x] `src/orion/__init__.py` com `__version__ = "0.1.0-alpha"`
  - [x] Ponto de entrada CLI `src/orion/cli.py` com o banner *The Hunter Crest* (Rich + Typer)
  - [x] Modelos de configuração tipados em `src/orion/config.py` (RoutingMode, AutonomyLevel, ProviderConfig, PathsConfig, OrionConfig — Pydantic v2 frozen)
  - [x] `tests/conftest.py`, `tests/unit/test_cli.py`, `tests/unit/test_config.py` — 41 testes, 100% passando
  - [x] Venv `.venv/` criado e `pip install -e ".[dev]"` funcional
  - [x] `orion --version` e `orion info` operacionais
- [x] **Sprint 2: Core ReAct Engine, Action-Observation EventBus & Artefatos** ✅ CONCLUÍDA (2026-10-24) — Cobertura: 96.24%
  - [x] `src/orion/core/errors.py` — Hierarquia tipada de exceções (OrionError, TurnBudgetExceeded, EngineStateError, PromptInjectionSuspected, ArtifactError, PEPDeniedError)
  - [x] `src/orion/core/events.py` — Modelos imutáveis Pydantic v2: Action, Observation, TurnStarted, Thinking, ActionEmitted, ObservationReceived, FinalAnswer, TurnCompleted
  - [x] `src/orion/core/event_bus.py` — Pub/Sub assíncrono in-process com buffer circular e isolamento de erros por handler
  - [x] `src/orion/core/state.py` — StateMachine com 9 estados e grafo de transições validado
  - [x] `src/orion/core/engine.py` — ReActEngine assíncrono com Turn Budgeting, delimitadores formais de prompt e proteção contra injeção
  - [x] `src/orion/artifacts/models.py` — ArtifactMetadata, Artifact, StorageScope (GLOBAL/LOCAL/BOTH)
  - [x] `src/orion/artifacts/store.py` — ArtifactStore com persistência dual e registro em memória
  - [x] `tests/unit/test_event_bus.py`, `test_engine.py`, `test_artifacts.py` — 59 novos testes, 100 total passando
- [x] **Sprint 3: As 5 Ferramentas Primitivas Nativas & PEP Determinístico** ✅ CONCLUÍDA (2026-10-24)
  - [x] Implementação de `permissions.py` (LEVEL_0 a LEVEL_3) e `WorkspaceScope`
  - [x] Implementação de `pep.py` (validação determinística e aprovação no modo supervisionado)
  - [x] `AuditLogger` append-only em `~/.orion/audit.log`
  - [x] `LocalRuntimeProvider` e as 5 ferramentas (`run_command`, `read_file`, `write_file`, `edit_file`, `search_files`)
  - [x] Testes unitários de ferramentas e segurança (168 testes totais passando)
- [ ] **Sprint 4: Testes E2E, Cobertura $\ge 85\%$ & Release**
  - [ ] Harness de testes de integração ponta a ponta
  - [ ] Testes de estresse de segurança (injeção, path traversal)
  - [ ] Aferição de cobertura $\ge 85\%$ com `pytest-cov`
  - [ ] Congelamento da v0.1.0 e tag Git

---

### [ESPECIFICAÇÃO CONCLUÍDA] Fase 2: v0.2.0 Cognitive Continuity: Triple Memory, Agent Skills Standard & Dynamic Compaction
- [x] Especificação formal da versão em `docs/planning/versions/v0.2.0/VERSION.md`
- [x] Especificação técnica de habilidades em `docs/architecture/AGENT_SKILLS_STANDARD.md`
- [x] Especificação técnica da Memória Tríplice em `docs/architecture/TRIPLE_MEMORY.md`
- [x] Especificação técnica de Timeline & Compactor em `docs/architecture/TIMELINE_SYSTEM.md`
- [x] As 4 Sprints detalhadas e congeladas:
  - [x] `sprints/sprint-1.md` (Main Timeline & SQLite FTS5 BM25)
  - [x] `sprints/sprint-2.md` (FastEmbed Local ONNX Vector & RRF Hybrid Fusion)
  - [x] `sprints/sprint-3.md` (Structured Knowledge, User Profile & Cognitive Memory Tools)
  - [x] `sprints/sprint-4.md` (Universal Skills Standard & Dynamic Compactor / Branches)
- [ ] Implementação de código e testes (aguardando execução após a v0.1.0)

---

### [ESPECIFICAÇÃO CONCLUÍDA] Fase 3: v0.3.0 Model Gateway, Real-Time Cost Ledger, Offline Resilience & Nuclear Safety
- [x] Especificação formal da versão em `docs/planning/versions/v0.3.0/VERSION.md`
- [x] As 4 Sprints detalhadas e congeladas:
  - [x] `sprints/sprint-1.md` (Model Registry & OpenRouter Provider Abstraction)
  - [x] `sprints/sprint-2.md` (Dynamic Auto-Routing & Complexity Engine)
  - [x] `sprints/sprint-3.md` (Real-Time Multi-Currency Cost Ledger & Budgeting)
  - [x] `sprints/sprint-4.md` (ORION Imortal Failover Local Leve Qwen Coder 1.5B/3B & Nuclear Step-Up Auth Gateway)
- [ ] Implementação de código e testes (aguardando execução após a v0.2.0)

---

### [ESPECIFICAÇÃO CONCLUÍDA] Fase 4: v0.4.0 High-Performance Stream CLI, Slash Commands & Native MCP
- [x] Especificação formal da versão em `docs/planning/versions/v0.4.0/VERSION.md`
- [x] Especificação de UX/UI em `docs/design/TUI_DESIGN_SYSTEM.md` e arte ASCII em `docs/design/ascii-art.txt`
- [x] As 4 Sprints detalhadas e congeladas:
  - [x] `sprints/sprint-1.md` (Stream CLI `orion-agent`, Banner da Mão Cósmica & Status Line)
  - [x] `sprints/sprint-2.md` (Prompt Interativo com `prompt_toolkit`, Autocomplete `/` e `@`)
  - [x] `sprints/sprint-3.md` (Streaming Vivo com `Rich.Live`, Diffs Cirúrgicos e 20 Slash Commands)
  - [x] `sprints/sprint-4.md` (Native MCP Client stdio/SSE & Integração com PEP)
- [ ] Implementação de código e testes (aguardando execução após a v0.3.0)

---

### [PLANEJADO] Fase 5: v0.5.0 Ambient Voice Daemon & Boot Headless
- [ ] Systemd user daemon rodando no boot do Linux
- [ ] Escuta contínua de wake word leve (openWakeWord)
- [ ] Transcrição Faster-Whisper e síntese Piper TTS com Tone-Mirroring
