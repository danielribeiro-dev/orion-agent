# O.R.I.O.N — Progress & Backlog Tracker
*(Operational Reasoning & Intelligence Orchestration Network)*

## 📊 Status Global do Projeto
- **Repositório:** `orion-agent`
- **Fase Atual:** Fase 0 Concluída & Validada — Especificação da v0.1.0 Fechada para Início
- **Linhas de Código em `src/`:** 0 (Aguardando autorização para iniciar a Sprint 1)

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

### [PRONTO PARA INICIAR] Fase 1: v0.1.0 Clean Foundation & Core ReAct Engine
- [ ] **Sprint 1: Tooling, Tipagem & Skeleton**
  - [ ] `pyproject.toml` moderno com PEP 621 e dependências
  - [ ] Ponto de entrada CLI `src/orion/cli.py` com o banner *The Hunter Crest*
  - [ ] Modelos de configuração tipados em `src/orion/config.py` (modos auto/fixed, provedores)
  - [ ] Testes unitários de infraestrutura
- [ ] **Sprint 2: Core ReAct Engine, Action-Observation EventBus & Artefatos**
  - [ ] Modelos de eventos tipados `Action` e `Observation` em Pydantic v2
  - [ ] `EventBus` pub/sub assíncrono in-process com histórico
  - [ ] `ReActEngine` assíncrono com Turn Budgeting (max 20 passos) e delimitadores de prompt
  - [ ] Subsistema `ArtifactStore` com suporte de persistência dual
  - [ ] Testes unitários do motor cognitivo
- [ ] **Sprint 3: As 5 Ferramentas Primitivas Nativas & PEP Determinístico**
  - [ ] Implementação de `permissions.py` (LEVEL_0 a LEVEL_3) e `WorkspaceScope`
  - [ ] Implementação de `pep.py` (validação determinística e aprovação no modo supervisionado)
  - [ ] `AuditLogger` append-only em `~/.orion/audit.log`
  - [ ] `LocalRuntimeProvider` e as 5 ferramentas (`run_command`, `read_file`, `write_file`, `edit_file`, `search_files`)
  - [ ] Testes unitários de ferramentas e segurança
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

### [PLANEJADO] Fase 3: v0.3.0 Model Gateway, Real-Time Cost Ledger & Offline Resilience
- [ ] Dynamic Auto-Routing com elevação para raciocínio pesado e retorno para execução leve
- [ ] Integração com OpenRouter e provedores diretos (Gemini, Anthropic, OpenAI, Ollama)
- [ ] Registro detalhado em `metrics.db` e comando `/cost`
- [ ] ORION Imortal: Detecção de queda em < 2s e Event Sourcing local

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
