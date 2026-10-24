# ORION-Agent — Progress & Backlog Tracker

## 📊 Status Global do Projeto
- **Repositório:** `orion-agent`
- **Fase Atual:** Fase 0 — Fundação Documental & Alinhamento Estratégico
- **Linhas de Código em `src/`:** 0 (Aguardando conclusão e aprovação da Fase 0)

---

## 🗺️ Roadmap de Fases

### [EM ANDAMENTO] Fase 0: Fundação Documental, Identidade e Governança
- [x] Inicialização do repositório Git local e configuração de usuário
- [x] Configuração da licença Apache 2.0 e .gitignore
- [x] Estrutura da memória persistente do agente em `.claudex/`
  - [x] `active_context.md`
  - [x] `progress.md`
  - [x] `system_patterns.md`
  - [x] `decisions.md`
- [x] Especificações Técnicas de Arquitetura em `docs/architecture/`
  - [x] `CORE_REACT_ENGINE.md` (Loop de raciocínio, Tool Calling, Delimitadores e State Machine)
  - [x] `TRIPLE_MEMORY.md` (Linha do tempo FTS5, ONNX/FastEmbed e fatos estruturados)
  - [x] `TIMELINE_SYSTEM.md` (Main Timeline, branches contextuais e retroalimentação)
  - [x] `AMBIENT_VOICE.md` (Daemon headless, Wake Word, Faster-Whisper, Piper e Tone-Mirroring)
  - [x] `MCP_AND_CHANNELS.md` (Cliente MCP, Telegram, WhatsApp e rotas HTTP genéricas)
  - [x] `GOVERNANCE_PEP.md` (Policy Enforcement Point, Sandbox, Permissões e Autonomia)
  - [x] `MODEL_GATEWAY_COSTS.md` (Multi-provedores, Ledger de Tokens e Custos USD/BRL)
- [x] Especificações de Superpoderes Modernizados em `docs/specs/superpowers/`
  - [x] `01_SPATIAL_INTERACTION_AND_VISION.md` (MediaPipe ONNX, Ray Casting, AT-SPI2 e Qwen2.5-VL)
  - [x] `02_GHOST_INPUT_AND_CDP.md` (CDP background, uinput Virtual HID e Write-Where-Pointed)
  - [x] `03_AUTONOMOUS_WEB_AND_VAULT.md` (Browser MCP, Zero-Knowledge Keyring e Biometria Vocal)
  - [x] `04_SELF_HEALING_AND_SANDBOX.md` (Tree-sitter multi-linguagem, Bubblewrap Sandbox e Auto-Cura)
  - [x] `05_IMMORTAL_OFFLINE_RESILIENCE.md` (Heartbeat, fallback local, Event Sourcing e reconciliação)
  - [x] `06_WORKFLOW_PROACTIVITY.md` (DBus hooks sem CPU, Git Guard, Protocolo Babá e Morning Summary)
- [x] Design System e Identidade Visual em `docs/design/`
  - [x] `ASCII_ART_IDENTITY.md` (Opções de ASCII Art e tema)
  - [x] `TUI_DESIGN_SYSTEM.md` (CLI dinâmica inspirada no Antigravity, slash commands, diffs)
- [x] Governança de Planejamento, Roadmap e Sprints em `docs/planning/`
  - [x] `ROADMAP.md` (Roadmap mestre com estratégia de superação do Hermes)
  - [x] `templates/TEMPLATE_VERSION.md` e `templates/TEMPLATE_SPRINT.md`
  - [x] `versions/v0.1.0/` (Spec da versão + Sprints 1 a 4)
  - [x] `versions/v0.2.0/` (Spec da versão + Sprints planejadas)
- [x] `README.md` completo e manifesto aberto do projeto
- [x] `LICENSE` (Apache 2.0) e `.gitignore` configurados

---

### [PLANEJADO] Fase 1: Fundação Limpa & Core ReAct Loop
- [ ] Setup de `pyproject.toml` (dependências: Rich, FastEmbed, Pydantic, etc.)
- [ ] Implementação do Core ReAct Loop com streaming assíncrono
- [ ] Implementação do PEP (Policy Enforcement Point) e Governança inicial
- [ ] RuntimeProvider com adaptador isolado do Hermes (temporário e desacoplado)
- [ ] Testes unitários do núcleo ReAct (cobertura >= 85%)

### [PLANEJADO] Fase 2: Linha do Tempo Contínua & Memória Tríplice
- [ ] Main Timeline persistente (SQLite WAL + FTS5 BM25)
- [ ] Branches contextuais com síntese de checkpoints
- [ ] Memória Semântica com ONNX/FastEmbed local
- [ ] Memória Estruturada (Perfil e Decisões)
- [ ] Testes de continuidade entre sessões

### [PLANEJADO] Fase 3: Gateway de Provedores & Cost Ledger
- [ ] Token & Cost Tracking em tempo real (USD/BRL)
- [ ] Roteamento dinâmico por capacidade e orçamento (OpenRouter, Gemini, Anthropic, OpenAI, Local)
- [ ] Testes de resiliência e circuit breaker

### [PLANEJADO] Fase 4: TUI Dinâmica, Slash Commands & Suporte a MCP
- [ ] Interface de terminal com streaming, status bar, diffs syntax highlighted
- [ ] Slash commands dinâmicos (`/plan`, `/config`, `/compact`, `/history`, etc.)
- [ ] Cliente MCP para carregamento universal de ferramentas da comunidade
- [ ] Editor cirúrgico de código nativo (Diff Match Patch)

### [PLANEJADO] Fase 5: Modo Ambiente & Pipeline de Voz Headless
- [ ] Daemon systemd de usuário em segundo plano (autostart no boot)
- [ ] Escuta e resposta ativas sem necessidade de terminal aberto
- [ ] Wake Word + Faster-Whisper + Piper TTS com Tone-Mirroring
- [ ] Conectores genéricos para Telegram, WhatsApp e Webhooks HTTP
