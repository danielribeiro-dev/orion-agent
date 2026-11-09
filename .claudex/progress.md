# O.R.I.O.N — Progress & Backlog Tracker
*(Operational Reasoning & Intelligence Orchestration Network)*

## 📊 Status Global do Projeto
- **Repositório:** `orion-agent`
- **Fase Atual:** Fase 5 (v0.5.0 Claude-Grade Agent) **EM ANDAMENTO** 🟡 (Sprint 0 concluída; v0.4.0 implementada, tags/merge pendentes)
- **Linhas de Código em `src/`:** ~16.300 linhas de produção
- **Testes:** 1747 passando, cobertura global 92% (medido em 09/11/2026 após a 6B; excluídos `test_vector_store` — baixa o modelo ONNX, sem rede aqui — e os 2 arquivos que importam `aiohttp`, dependência não declarada no `pyproject.toml`) ✅

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

### [IMPLEMENTADA] Fase 4: v0.4.0 High-Performance Stream CLI, Slash Commands & Native MCP
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
- [x] **Sprint 3: Refinamento Estético, Geometria Anti-Emoji & Dynamic Prompt** ✅ CONCLUÍDA
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

### [EM ANDAMENTO] Fase 5: v0.5.0 Claude-Grade Agent (Paridade Claude Code)
Especificação: `docs/planning/versions/v0.5.0/VERSION.md`. Voz e daemon de voz migraram para a v0.6.0 (ADR-020).
- [x] **Sprint 0: Higiene & Fundação** ✅ CONCLUÍDA (2026-11-06) — docs reconciliados, ADR-020/021/022, `CLAUDE.md`, baseline (`docs/planning/versions/v0.5.0/baseline.md`)
- [x] **Sprint 1: Provider Anthropic Nativo** ✅ IMPLEMENTADA (2026-11-06; commit pendente)
  - [x] `ContentBlock`/`ToolSpec`/`ToolChoice`/`ThinkingConfig`/`CacheControl`; `LLMRequest.system/tools/tool_choice/thinking/cache_control`; adaptador `flatten_content`/`to_blocks` para providers legados
  - [x] `gateway/providers/anthropic.py` (SSE tipado, thinking com assinatura, tool_use, cache, `count_tokens`), `errors.py`, retry/reconexão de `stream()` em `providers/base.py` (também OpenRouter; 5xx agora retentado em `complete()`)
  - [x] Registry Claude 5 (preços da tabela Anthropic de 06/10/2026), tiers nativos, cache read/write precificados e persistidos no ledger (migração de coluna)
  - [x] `gateway/failover.py` (Anthropic -> OpenRouter -> Ollama; downgrade só com `ORION_ALLOW_DOWNGRADE=1`), breaker ligado à `AgentSession` e ao PEP, `gateway/credentials.py` + `/doctor`
  - [x] Testes: `test_anthropic_provider.py`, `test_failover.py`; live opt-in `test_anthropic_live.py` (`ORION_LIVE=1 pytest -m live`) — NÃO executado (sem chave)
  - Decisões: erro no meio do stream não reinicia (vira `StreamInterruptedError`); `temperature` nunca enviada; `tool_choice` forçado vira `auto` em Fable 5.1/Opus 5.5/Sonnet 5.5; slug OpenRouter `anthropic/<id>` NÃO verificado
- [x] **Sprint 2: Loop Agêntico Nativo** ✅ IMPLEMENTADA (2026-11-06; commit pendente)
  - [x] `BaseTool` com `name/description/input_schema/read_only`; schemas nas 5 tools primitivas, `memorize/recall/deprecate_fact/inspect_environment`, `use_skill`, `mcp_schema` e adaptadores MCP (schema do servidor); `jsonschema` declarado em `pyproject.toml`
  - [x] `LocalRuntimeProvider.validate_params/tool_specs/is_read_only`: params inválidos voltam como `tool_result` com `is_error`, antes do PEP e sem executar
  - [x] Fonte única de risco em `governance/permissions.py` (`tool_risk_level`, `is_read_only_tool`, `risk_to_action_level`); `_RISK_MAP` removido. Tools cognitivas ganharam nível PEP explícito (recall/inspect/use_skill = LEVEL_1; memorize/deprecate_fact = LEVEL_2) — antes caíam no default LEVEL_3
  - [x] `core/engine.py` reescrito: `ModelTurn`, `stop_reason` (`tool_use`, `max_tokens` com até 3 continuações, `refusal`, `end_turn`), tools read-only consecutivas em paralelo e mutantes em série (mutante é barreira), cancelamento fecha `tool_use` pendente com `tool_result` sintético, saída de tool delimitada e delimitadores forjados desarmados; system prompt estável (sem contador de turnos) para cache
  - [x] `AgentSession`: `TOOL_PROTOCOL`/`ToolCallFilter` removidos; `_llm` devolve `ModelTurn` a partir dos chunks tipados; histórico guarda `tool_use`/`tool_result` reais (preservado no cancelamento); `compact()` agrupa por turno; `max_tokens` 16k no Anthropic; renderer com cards paralelos (chave = action_id)
  - [x] Testes: `test_engine_toolcalls.py`, `test_tool_schemas.py`, helper `tests/llm_script.py`; suítes antigas migradas para o novo contrato do LLM (stub `(prompt)->tuple` virou `ScriptedLLM`)
  - Limitação conhecida: OpenRouter/Ollama (e o destino de failover) ainda não recebem `tools`: respondem só texto até serem portados para tool calling nativo (movido para o escopo da Sprint 3). `mcp_schema` segue registrada, mas redundante (as tools MCP agora levam o schema completo)
- [x] **Sprint 3: Contexto, Sessões & Memória** ✅ IMPLEMENTADA (2026-11-07; commit pendente)
  - [x] Prompt em camadas (`compose_system` + `LAYER_BREAK`: identidade/regras · manifest+skills · `CLAUDE.md`/`ORION.md` · avisos), breakpoint de cache Anthropic no fim das camadas estáveis, `cache_hit_ratio()` no `/context`
  - [x] `timeline/autocompact.py`: poda a 60%, compactação a 80% (LLM FAST com fallback determinístico, intra-turno, pedido ativo verificado), calibração pelo `prompt_tokens` real; gancho `prepare_messages` no engine; teto de saída por tool (`truncate_output`)
  - [x] Wiring na `AgentSession`: `SkillsEngine`, `CognitiveManifestGenerator`, `EnvironmentMonitor`, `MemoryFileSyncer` (MEMORY.md), `AutoRecall` (HybridRetriever, 1500 tokens, BM25 de fallback) também como retriever do tool `recall`
  - [x] `sessions/` (JSONL por workspace, blobs 0600, `replay`, `rewind` atômico, restauração de arquivos sem clobber), `/resume`, `/rewind`, `--continue`/`--resume`
  - [x] `record_decision` (PEP LEVEL_3; fato CONFIRMED + `.orion/decisions/NNNN-slug.md`); `/plan` e `/grill-me` instruem o registro
  - [x] OpenRouter/Ollama com tool calling nativo (`openai_wire.py`), degradação a texto com aviso, failover preservando tools e `tool_result`; `mcp_schema` removida
  - [x] Testes: `test_autocompact.py`, `test_sessions.py`, `test_decisions.py`, `test_legacy_tool_calling.py` (servidor HTTP simulado); suíte 1293 verdes, cobertura global 94%
  - Pendente: validar compactação/caching com provedor real (`ORION_LIVE=1`); ruff/mypy têm backlog pré-existente (74/31 → sem novos erros)
- [x] **Sprint 4: Paridade de Ferramentas** ✅ IMPLEMENTADA (2026-11-07; commit pendente) — **portão de dogfooding pendente** (`docs/planning/versions/v0.5.0/dogfooding-gate.md`)
  - [x] `read_file` (offset/limit, numeração, imagem como bloco `image`, PDF via `pdftotext`), `edit_file(replace_all)`, `glob`, `grep` (ripgrep ou Python), `notebook_edit`
  - [x] `web_fetch`/`web_search` (LEVEL_2): allowlist, anti-SSRF por redirect, 2 MB, conteúdo neutralizado e rotulado como não confiável
  - [x] `todo_write` (card na TUI), `ask_user` e `enter/exit_plan_mode` (modais; LEVEL_0, `SERIAL_TOOLS`), `run_command(run_in_background)` + `bash_output` + `kill_shell`
  - [x] Imagens: `@arquivo.png` anexa bloco de imagem (só modelos Anthropic; aviso nos demais); `engine.run(images=...)`
  - [x] **Startup:** stderr do MCP e logs da CLI redirecionados para `~/.orion/logs/`; tela limpa no boot e prompt ancorado no rodapé
  - [x] Testes: `test_tools_read_search`, `test_tools_web`, `test_tools_shell_flow`, `test_sprint4_integration`; cobertura global 94%; mypy 30 → 26 erros (backlog pré-existente, nenhum novo)
  - Pendente: executar o portão com chave real; colar imagem da área de transferência (adiado); modais verificados por teste de lógica, não em TTY interativo real
- [x] **Sprint 5: Extensibilidade & MCP Completo** ✅ IMPLEMENTADA (2026-11-08; 5A e 5B em commits locais, sem push)
  - [x] 5A `settings/` (user < projeto < local; migração do `config.json`; escrita atômica 0600; confiança TOFU por hash em `~/.orion/trusted_projects.json`)
  - [x] 5A regras `allow/ask/deny` no PEP (`governance/rules.py`; deny > ask > allow; allow não casa comando composto); "sempre permitir" persiste na camada local
  - [x] 5A **sudo e fora do workspace viram pergunta** com motivo (uso único; sem humano = negado; nuclear e safe-holding seguem bloqueio duro); modo plano somente leitura no PEP
  - [x] 5A auditoria: `decision_source`, negações completas, `pending` fechado, `action_id` do engine propagado (`CURRENT_ACTION_ID`)
  - [x] 5A `hooks/` (8 eventos; exit 2 bloqueia; hook nunca aprova; auditados; saída neutralizada), comandos custom `.md`, `/skills`, plugin mínimo
  - [x] 5A testes: `test_settings`, `test_permission_rules`, `test_hooks`, `test_custom_commands`; suíte inteira verde, cobertura 94%, mypy sem erros novos (26 de backlog)
  - [x] ADR-023/024/025; `CLI_AGENT_RULES.md` seção 2
  - [x] Segurança de teste: fixture autouse em `tests/conftest.py` impede abrir o desafio nuclear real (zenity/kdialog/tty) — um teste chegou a abrir um popup real durante o desenvolvimento
  - [x] 5B MCP: streamable HTTP, headers `${VAR}`, OAuth PKCE (tokens 0600, login só sob demanda), resources (`@srv:uri`, tools LEVEL_1), prompts como slash commands, `list_changed`, keepalive e reconexão com backoff, `/mcp add|remove|auth|resources|prompts`
  - [x] 5B testes: `test_mcp_http_oauth` com servidor MCP real em subprocesso (`tests/fixtures/mcp_http_server.py`, inclui OAuth/PKCE); suíte inteira verde, cobertura 93,7%, mypy sem erros novos (26 de backlog)
  - [x] ADR-026; `docs/architecture/MCP_AND_CHANNELS.md` §1.1; `mcp>=2.3` + `httpx2` no `pyproject.toml` e `uv.lock` atualizado offline
- [x] Sprint 6: Subagents & Tasks ✅ IMPLEMENTADA (6A + 6B, 09/11/2026) — spec congelada em 08/11/2026: 6A (núcleo foreground) e 6B (background/tasks/worktree/loop); ADR-028 a 031; estudo comparativo em `docs/planning/versions/v0.5.0/sprint-6-study.md`
  - [x] **6A ✅ IMPLEMENTADA (2026-11-09; commit local, sem push)** — núcleo foreground, seguro e medido
    - [x] `agents/`: `definitions.py` (4 embutidos `explore|plan|general-purpose|code-review`; `.md` com frontmatter em `.orion/agents`, `~/.orion/agents`, plugin e `.claude/agents` com campos de privilégio descartados; TOFU por hash do conjunto — agente de projeto sem confiança só lê), `runner.py`, `budget.py`, `ports.py` (6 portas + `ModelGatewayPort`), `refs.py`, `models.py`
    - [x] **Teto no PEP** (`PolicyEnforcementPoint.for_subagent`): `min(modo)` vivo, `deny`/`ask` do pai unidos (vivos), `allow` e trust ledger nunca herdados, plan mode e safe-holding do pai herdados, `cwd` confinado ao escopo; **`interactive=False` nega todo `ask` e o desafio nuclear** (nunca abre o prompt do SO); filho nunca é interativo nem grava regra
    - [x] `AgentRunner`: engine/bus/transcript/`AutoCompactor`/`HookRunner`/PEP por filho; system mínimo; tools = interseção com o pai (+ `FORBIDDEN_FOR_CHILD`, `disallowed_tools`); profundidade 1 (`max_depth` configurável, neto nunca excede o filho); isolamento pedido sem `WorkspacePort` **falha fechado**; resultado completo em `~/.orion/agents/<id>/` e `ref://` legível por `read_file`; `output_schema` validado; retomada de parcial reutiliza o modelo gravado
    - [x] Orçamento: `AgentBudget` → `AggregateBudget` → teto diário com **reserva antecipada** (pior caso = prompt + `max_tokens`); estouro/turnos/tempo/diário devolvem `partial_*` retomável; `ConcurrencyGate` (`max_concurrent`) vale no código
    - [x] Tool `task` (LEVEL_1, paralela, lote `tasks`); `SubagentStarted/Completed`, hooks `SubagentStart/SubagentStop` (só bloqueiam), `agent_id` na auditoria e nos eventos
    - [x] Gateway: `gateway/agent_gateway.py` (`build_llm_request`/`consume_stream` agora também usados por `AgentSession._llm`; `AgentGateway` sem tocar breaker/renderer/status bar/contadores; provider de filho com **breaker próprio** e sem downgrade); router com `models.tiers` (lista ordenada) e `resolve_for_agent` (sem downgrade silencioso: mutante exige tier ≥ balanced; só leitura pode cair para o local); `ModelSpec.supports_prompt_cache/supports_tool_use`
    - [x] Ledger: colunas `origin` e `agent_id` (migração `ALTER` idempotente), `spent_by_agent/origin/agents`; settings `agents.*` e `models.{tiers,profiles}` (camada de projeto só vale confiada)
    - [x] TUI: `/agents [list|show|runs|trust]` (catálogo 26 → 27), `/review` reescrito sobre `code-review` (diff vai como contexto do filho), `/cost` e status bar somam filhos, linha compacta por filho (sem `Live`), `ChangeTracker`/`/undo`/`/rewind` com `agent_id`
    - [x] Testes (+185): `test_agent_definitions`, `test_agent_privilege` (inclui propriedade "filho nunca excede o pai" em 3 modos × plan × 10 ações), `test_agent_budget`, `test_subagents`, `test_subagents_session`, `test_agent_gateway`, `test_agent_settings`; 1670 passam, cobertura 92% (sem `test_vector_store`/`aiohttp`, ver nota), ruff 73 (= baseline), mypy sem erros novos além do ruído de ambiente `BaseModel: Any`
    - Pendente (exige o Senhor): validação manual em TTY real (`/agents`, linhas de progresso) e rodada live no `explore` com `ORION_LIVE=1` + teto no `BudgetGuard`
  - [x] **6B ✅ IMPLEMENTADA (2026-11-09; commit local, sem push)** — background, tasks, worktree, `/loop`
    - [x] `agents/loop_thread.py`: `ThreadExecutor` (loop asyncio persistente em thread daemon; `copy_context` ao despachar; `cancel`/`cancel_all`/`shutdown` em cascata) e `NotificationQueue` (fila thread-safe, drenada antes de cada prompt; a toolbar mostra `tasks N ● · M ✔`); `Ctrl+C` cancela o turno, não as tasks
    - [x] `agents/tasks.py`: `SqliteTaskStore` (`~/.orion/tasks.db`, WAL, parametrizado, 0600) e `TaskManager` (start/stop/stop_all/wait/send_message/recover; tasks de processos mortos viram `interrupted` pelo `pid`); tools `task_create/list/get/stop` e `send_message` (níveis no `TOOL_LEVELS`; nenhuma vai a subagents); término chega por evento e entra no PRÓXIMO turno do modelo como `Background events` (dado não confiável); zero token enquanto espera
    - [x] `send_message`: caixa de entrada por filho (`AgentInbox`) lida entre as chamadas dele, anexada à última mensagem de usuário (papéis alternam); retomada de parcial reutiliza id e modelo
    - [x] `agents/worktree.py`: `GitWorktreeWorkspace` (`git worktree add --detach` em `~/.orion/worktrees/`, removido se sem mudanças, mantido e reportado se com); caminhos relativos/`cwd` ancorados na raiz; PEP confina `cwd` e leituras; **falha fechada** fora de git/sem commit; liberado também ao cancelar
    - [x] `agents/loops.py` + `/loop`: disparo = subagent de orçamento/turnos limitados com origem `loop`; **triagem** determinística (impressão digital do repo) antes do modelo, tier `fast` com `max_tokens` 8 só se inconclusiva; expiração 7 dias, teto de disparos (50), no máx. 5 loops, intervalo mínimo 30 s, intervalo dinâmico que se espaça sem novidade
    - [x] TUI: `/tasks [list|get|stop]` (também lista/encerra shells), `/loop [intervalo] [flags] <meta> | list | stop`, status bar com tasks, catálogo 27 → 29, `refresh_interval` do prompt
    - [x] Correções de base achadas no caminho: `ShellManager` com `log_path` único por instância; `JsonlSessionStore.append` com lock (filhos em background gravam de outra thread); **`WorkspaceScope` agora expande `~`** (antes `~/x` era tratado como subpasta literal do cwd e tools que expandem, como `notebook_edit`, escapavam do escopo)
    - [x] Testes (+137): `test_agent_executor`, `test_tasks`, `test_worktree` (git real; mutação confirmou que os testes quebram sem a ancoragem/confinação), `test_loop`, `test_background_session`, `test_agent_infra`; 1747 passam, cobertura 92%, ruff 73 (= baseline), mypy sem erros novos além do ruído `BaseModel: Any`
    - Pendente (exige o Senhor): TTY real (notificação entre turnos, toolbar, `/tasks`, `/loop`) e rodada live com `ORION_LIVE=1`; persistência durável de `/loop` e cron real ficam para a Sprint 7
  - [x] **Gates zerados (2026-11-09)** — `1ae924f` (ruff 73 → 0; `StrEnum`, `per-file-ignores` de `SIM117`/`B017` em `tests/**`) e `3e9d210` (mypy strict 21 → 0); 1815 testes, cobertura 94,19%; branch enviada ao remoto
- [ ] Sprint 7: Daemon, Jobs & Schedules
- [ ] Sprint 8: Hardening & Release
- [ ] Pendências herdadas da v0.4.0: tags `v0.3.0`/`v0.4.0` e merge em `main`; validar turno com provedor real; repetir A/B de MCP com modelo pago

---

### [PLANEJADO] Fase 6: v0.6.0 Ambient Voice Daemon
- [ ] Wake word (openWakeWord), Faster-Whisper, Piper TTS com Tone-Mirroring, sobre o daemon da v0.5.0
