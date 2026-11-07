# O.R.I.O.N — Progress & Backlog Tracker
*(Operational Reasoning & Intelligence Orchestration Network)*

## 📊 Status Global do Projeto
- **Repositório:** `orion-agent`
- **Fase Atual:** Fase 4 (v0.4.0) **EM ANDAMENTO** 🟡 (Sprint 1 Concluída)
- **Linhas de Código em `src/`:** ~2.300 linhas de produção testadas
- **Testes:** 887/887 passando (100% sucesso) ✅ (838 das versões v0.1.0-v0.3.0 + 49 da Sprint 1 v0.4.0)

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

### [CONCLUÍDO] Fase 1: v0.1.0 Clean Foundation & Core ReAct Engine
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
- [x] **Sprint 4: Testes E2E, Cobertura $\ge 85\%$ & Release** ✅ CONCLUÍDA (2026-10-25) — 210 testes · Cobertura: 92.57%
  - [x] 10 testes E2E de fluxo ReAct em `tests/e2e/test_react_flow.py`
  - [x] 32 testes de segurança/auditoria em `tests/e2e/test_security_audit.py`
  - [x] Cobertura global ≥ 85% confirmada (92.57%)
  - [x] README.md atualizado com instruções de instalação e testes
  - [x] VERSION.md congelada · sprint-4.md marcada como concluída
  - [x] Tag Git `v0.1.0` criada

---

### [EM ANDAMENTO] Fase 2: v0.2.0 Cognitive Continuity: The 5-Sphere Memory, Universal Skills Standard & Dynamic Compaction
- [x] Especificação formal da versão em `docs/planning/versions/v0.2.0/VERSION.md` (As 5 Esferas Cognitivas, PCU, Headroom Guard e Telegram HITL)
- [x] Especificação técnica de habilidades em `docs/architecture/AGENT_SKILLS_STANDARD.md`
- [x] Especificação técnica da Memória Tríplice & 5 Esferas em `docs/architecture/TRIPLE_MEMORY.md`
- [x] Especificação técnica de Timeline & Compactor em `docs/architecture/TIMELINE_SYSTEM.md`
- [x] As 4 Sprints detalhadas e congeladas com as 5 Esferas e PCU
- [x] **Sprint 1: Main Timeline & SQLite FTS5 BM25** ✅ CONCLUÍDA (2026-10-25) — Cobertura: 92%
  - [x] `src/orion/memory/models.py` (TimelineRecord, DayMarkerRecord e contratos das 5 esferas)
  - [x] `src/orion/memory/timeline.py` (TimelineManager com WAL, FTS5 BM25, DayMarkers)
  - [x] `tests/unit/test_timeline.py` (22 testes passando, verificação de concorrência e busca)
- [ ] **Sprint 2: FastEmbed Local ONNX Vector & RRF Hybrid Fusion** 🟡 EM ANDAMENTO
  - [x] `pyproject.toml` atualizado com `aiosqlite`, `fastembed`, `numpy`, `psutil`
### [CONCLUÍDO] Fase 2: v0.2.0 Cognitive Continuity & Triple Memory
- [x] Especificação formal da versão em `docs/planning/versions/v0.2.0/VERSION.md`
- [x] **Sprint 1: Main Timeline & SQLite FTS5** ✅ Concluída
  - [x] `src/orion/memory/models.py` (Modelos Pydantic v2 do subsistema de memória)
  - [x] `src/orion/memory/timeline.py` (TimelineManager SQLite WAL + FTS5 BM25 + DayMarkers)
  - [x] Testes unitários `tests/unit/test_timeline.py` (22 testes passando)
- [x] **Sprint 2: FastEmbed Local & RRF Fusion** ✅ Concluída
  - [x] Dependências (`aiosqlite`, `fastembed`, `numpy`, `psutil`, `pyyaml`)
  - [x] `src/orion/memory/vector_store.py` (VectorStore com FastEmbed `bge-small-en-v1.5`, dedup $\ge 0.92$, NumPy dot product)
  - [x] `src/orion/memory/hybrid_retriever.py` (HybridRetriever com RRF $k=60$ e controle de token budget de 1500 tokens)
  - [x] Testes unitários `tests/unit/test_vector_store.py` e `tests/unit/test_hybrid_retriever.py`
- [x] **Sprint 3: The 5-Sphere Memory, Cognitive Tools & Remote HITL Connector** ✅ Concluída
  - [x] `src/orion/runtime/environment.py` (EnvironmentMonitor com HeadroomGuard determinístico)
  - [x] `src/orion/core/identity.py` (IdentityManager com Origem Imutável e Persona Modular Jarvis)
  - [x] `src/orion/memory/facts_store.py` (FactsStore SQLite com máquina de estados anti-poisoning)
  - [x] `src/orion/memory/manifest.py` (CognitiveManifestGenerator com teto estrito de 250 tokens)
  - [x] `src/orion/memory/file_syncer.py` (MemoryFileSyncer com teto estrito de 200 linhas em MEMORY.md)
  - [x] `src/orion/memory/hitl_telegram.py` (TelegramHITLConnector com aprovação PEP remota e mock)
  - [x] `src/orion/memory/tools.py` (MemorizeTool, RecallTool, DeprecateFactTool, InspectEnvironmentTool)
  - [x] Testes unitários das 5 esferas (104 testes passando)
- [x] **Sprint 4: Universal Skills Standard & Dynamic Compactor / Branches** ✅ Concluída
  - [x] `src/orion/skills/` (SkillsLoader com precedência Workspace > Global > Builtin, `use_skill` tool, `SKILL.md`)
  - [x] `src/orion/builtin/skills/system-doctor/SKILL.md` (Habilidade nativa de auditoria de sistema)
  - [x] `src/orion/timeline/compactor.py` (ContextCompactor com teto 80%, comando `/compact`, preservação de vital tail e arquivos ativos)
  - [x] `src/orion/timeline/branch_manager.py` (BranchManager para `/branch`, `/merge` e arquivamento)
  - [x] `src/orion/timeline/checkpoint_synthesis.py` (Síntese executiva de 3 a 5 linhas)
  - [x] Testes unitários (24 testes passando: `test_skills_loader.py`, `test_compactor.py`, `test_branches.py`)
  - [x] Cobertura global atingida: 93.39% (389 testes passando, 0 falhas)

---

### [CONCLUÍDO] Fase 3: v0.3.0 Model Gateway, Real-Time Cost Ledger, Offline Resilience & Nuclear Safety
- [x] Especificação formal da versão em `docs/planning/versions/v0.3.0/VERSION.md`
- [x] As 4 Sprints concluídas e verificadas (838 testes unitários passando):
  - [x] **Sprint 1: Model Registry & OpenRouter Provider** ✅ CONCLUÍDA
  - [x] **Sprint 2: Dynamic Auto-Routing & Complexity Engine** ✅ CONCLUÍDA
  - [x] **Sprint 3: Real-Time Multi-Currency Cost Ledger & Budget Guard** ✅ CONCLUÍDA
  - [x] **Sprint 4: Resiliência Universal, Salvaguarda Cognitiva & Nuclear Step-Up Auth** ✅ CONCLUÍDA
- [x] Tag Git e commits finalizados no ramo `version/v0.3.0`.

---

### [EM EXECUÇÃO] Fase 4: v0.4.0 High-Performance Stream CLI, Slash Commands & Native MCP
- [x] Especificação formal da versão em `docs/planning/versions/v0.4.0/VERSION.md`
- [x] Design System de Cores oficial "Deep Cosmos & Glacial Platinum" em `docs/design/ASCII_ART_IDENTITY.md` e `TUI_DESIGN_SYSTEM.md`
- [x] Decisão arquitetural: Cockpit imersivo eDEX desacoplado para a v0.7.0 (Desktop App dedicado via Tauri v2 / WebGL com tokens do Figma)
- [x] As 4 Sprints detalhadas e congeladas com contratos tipados e wireframes em ASCII
- [x] **Sprint 1: Stream CLI Foundation, Design System Cósmico & Banner Adaptativo** ✅ CONCLUÍDA (2026-10-26) — Cobertura: 98.32%
  - [x] Ponto de entrada executável `orion-agent` e `orion` configurados no `pyproject.toml`
  - [x] Mapeamento oficial de cores Deep Cosmos & Glacial Platinum em `src/orion/tui/theme.py` e singleton `src/orion/tui/console.py`
  - [x] Renderizador adaptativo `src/orion/tui/banner.py` (Stellar Cyber Block < 100 cols, Event Horizon com gradiente cósmico `#00D2FF` -> `#3A7BD5` >= 100 cols)
  - [x] Modelo e barra de status dinâmica `src/orion/tui/status_bar.py` (Pydantic v2, badges com fallback resiliente de identidade, livro-razão financeiro USD/BRL)
  - [x] Integração de inicialização limpa sem flickering no CLI em `src/orion/cli.py`
  - [x] Suíte de 49 testes unitários implementada (`test_theme.py`, `test_banner.py`, `test_status_bar.py`, `test_cli.py`), 887 testes globais passando sem regressão
- [x] **Sprint 2: Terminal Engine, Prompt Interativo & Autocomplete** ✅ CONCLUÍDA (2026-10-26) — Cobertura TUI: 95.69%
  - [x] Dependência `prompt-toolkit>=3.0.40` adicionada no `pyproject.toml`
  - [x] Módulo `src/orion/tui/completer.py` com `OrionCompleter`, `SlashCommandCompleter` (/), `PathMentionCompleter` (@), `GitIgnoreMatcher`, e parser/resolver seguro de menções
  - [x] Módulo `src/orion/tui/keybindings.py` com atalhos `Ctrl+C` (interrupção graciosa sem matar processo), `Alt+Enter` (multilinha) e `Ctrl+L` (limpar tela)
  - [x] Módulo `src/orion/tui/prompt.py` com `InteractivePrompt`, histórico persistente em `~/.orion/history`, layout Rich integrado no bottom toolbar e execução resiliente com `TurnCancelledEvent`
  - [x] Evento `TurnCancelledEvent` adicionado em `src/orion/core/events.py`
  - [x] Suíte de 41 testes unitários (`test_completer.py`, `test_prompt_session.py`), totalizando 928 testes globais passando com 100% de sucesso
- [x] **Sprint 3: Refinamento Estético, Geometria Anti-Emoji & Dynamic Prompt**
- [x] **Sprint 4: Streaming Vivo, Diffs Cirúrgicos & 23 Slash Commands** (falta validar com provedor real)
  - [x] `StreamRenderer`, `DiffViewer`, painéis dos blueprints e modais com teclado
  - [x] `AgentSession`: ponte Gateway → ReAct → PEP, custos, conversa, `/undo`, branches de contexto
  - [x] Modos `plan`, `accept-edits`, `auto`, `manual` ligados ao PEP
- [x] **Sprint 5: Native MCP Client stdio/SSE & Integração com PEP + Starter Pack**
  - [x] `src/orion/mcp/` (models, client, transports, adapter lazy, runner em thread, spawn_policy) + `mcp_servers.default.json` (Serena e Context7 ON read-only; Sequential Thinking OFF)
  - [x] PEP dinâmico por tool (`register_tool_level`), SAFE_HOLDING cobre tools MCP mutadoras, `/mcp list|enable|disable|ping|tools`
  - [x] 31 testes MCP (incl. handshake stdio real); `ORION_MCP=0` desliga o cliente
  - [x] Versões fixadas (serena-agent 2.1.0, context7-mcp 4.5.1, sequential-thinking 2.1.1), SSE real, `RecallTool` corrigido, benchmark determinístico em `docs/planning/versions/v0.4.0/benchmarks/`
  - [~] A/B com LLM real: parcial (4/8 execuções válidas, sem conclusão); bugs do `search_files` corrigidos
  - [ ] Repetir A/B com modelo pago; injetar `HybridRetriever` na sessão; erro de autodetecção de linguagem do Serena

---

### [PLANEJADO] Fase 5: v0.5.0 Ambient Voice Daemon & Boot Headless
- [ ] Systemd user daemon rodando no boot do Linux
- [ ] Escuta contínua de wake word leve (openWakeWord)
- [ ] Transcrição Faster-Whisper e síntese Piper TTS com Tone-Mirroring
