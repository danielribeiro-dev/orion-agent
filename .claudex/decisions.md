# ORION-Agent — Architecture Decision Records (ADRs)

Este arquivo registra todas as decisões estruturais tomadas no projeto, seu contexto, racional e consequências.

---

### ADR-001: Repositório Novo e Clean Slate para Código
* **Status:** Aprovado (24/10/2026)
* **Contexto:** O repositório legado continha código experimental de diversas fases com acoplamentos a versões antigas de intents rígidos e dependências parciais.
* **Decisão:** Criar o repositório `orion-agent` do zero. Nenhuma linha de código `.py` legada é copiada diretamente; aproveitamos apenas as lições aprendidas e documentações conceituais.
* **Consequências:** Base de código 100% moderna, sem dívida técnica inicial, tipada e com arquitetura orientada a contratos.

---

### ADR-002: Núcleo Aberto (Open Source) com Integrações Agnósticas
* **Status:** Aprovado (24/10/2026)
* **Contexto:** A plataforma ORION será distribuída como produto de código aberto para a comunidade.
* **Decisão:** Nenhuma ferramenta ou serviço proprietário será hardcodado no núcleo. Todas as integrações com sistemas externos, canais (WhatsApp, Telegram) ou agentes terceiros serão configuradas dinamicamente pelo usuário via Model Context Protocol (MCP), webhooks HTTP ou arquivos de configuração do usuário.
* **Consequências:** O ORION torna-se um orquestrador universal aplicável a qualquer ecossistema profissional ou pessoal.

---

### ADR-003: Presença Ambiente Headless com Interface Sob Demanda
* **Status:** Aprovado (24/10/2026)
* **Contexto:** O conceito de J.A.R.V.I.S. exige que o usuário converse com o computador sem a cerimônia de abrir terminais.
* **Decisão:** O ORION roda como serviço contínuo em segundo plano (systemd user daemon). A interface de voz opera de forma headless (escuta e fala ativas sem janelas abertas). A TUI interativa é aberta sob demanda quando o usuário deseja programar ou realizar tarefas visuais.
* **Consequências:** Separação clara entre a camada de daemon de fundo e as superfícies de interface do usuário.

---

### ADR-004: Memória Tríplice (FTS5 + ONNX/FastEmbed + Fatos Estruturados)
* **Status:** Aprovado (24/10/2026)
* **Contexto:** Bancos vetoriais puros sofrem de alucinação de similaridade, falta de ordenação temporal e dependências pesadas de bibliotecas (como PyTorch completo).
* **Decisão:** Adotar a arquitetura de Memória Tríplice (v0.2.0):
  1. *Linha do tempo cronológica e busca exata:* SQLite com FTS5 (BM25).
  2. *Busca semântica conceitual:* ONNX / FastEmbed local (leve, sem PyTorch, 100% offline).
  3. *Fatos confirmados e perfil:* Armazenamento estruturado JSON/SQLite.
* **Consequências:** Alta velocidade, funcionamento offline, zero vazamento de dados e recuperação de contexto contextual precisa.

---

### ADR-005: Soberania Operacional das 5 Ferramentas Primitivas Nativas
* **Status:** Aprovado (24/10/2026)
* **Contexto:** Na concepção inicial cogitou-se usar o Hermes Agent como ponte temporária para I/O na v0.1.0. No entanto, agentes de ponta como Claude Code e Antigravity provam que uma fundação sólida deve ter ferramentas primitivas nativas, atômicas e testáveis.
* **Decisão:** Implementar nativamente em `src/orion/runtime/tools/` as 5 ferramentas primitivas puras: `run_command`, `read_file`, `write_file`, `edit_file` (substituição exata de bloco ancorado) e `search_files`. O Hermes Agent torna-se apenas um adaptador plugável e opcional, nunca uma dependência obrigatória.
* **Consequências:** Soberania técnica, zero dependências circulares de agentes terceiros, facilidade de mock e teste unitário com 100% de isolamento.

---

### ADR-006: Governança Progressiva (Modo Supervisionado Inicial com PEP)
* **Status:** Aprovado (24/10/2026)
* **Contexto:** Segurança e previsibilidade em execuções de ações reais no sistema operacional.
* **Decisão:** O ORION inicia em Modo Supervisionado, exigindo confirmação explícita `[Y/n]` do usuário para ações modificadoras (LEVEL_2 e LEVEL_3). O usuário pode customizar políticas de autonomia globalmente ou por sessão através de `/config` ou comandos naturais.
* **Consequências:** Prevenção contra danos ao ambiente de trabalho e total transparência operacional.

---

### ADR-007: Alinhamento Documental Prévio (Doc-First Engineering)
* **Status:** Aprovado (24/10/2026)
* **Contexto:** Evitar desenvolvimento caótico ou desalinhado entre o usuário e o assistente de IA.
* **Decisão:** Nenhuma linha de código executável em `src/` será escrita antes que todas as especificações arquiteturais, identidade visual (ASCII art) e o sistema de governança estejam aprovados.
* **Consequências:** Clareza absoluta de requisitos, ausência de retrabalho e rastreabilidade total.

---

### ADR-008: Padrão Action-Observation Event Stream & Subsistema de Artefatos
* **Status:** Aprovado (24/10/2026)
* **Contexto:** O loop cognitivo precisa suportar auditoria imutável (Event Sourcing), turn budgeting (teto de 20 voltas), saída desacoplada de relatórios técnicos e orquestração de subagentes reativos.
* **Decisão:** Adotar o padrão Action-Observation tipado com Pydantic v2 no `EventBus` e construir o subsistema de Artefatos (`ArtifactStore`) com modelo de persistência dual: global `~/.orion/brain/<session_id>/artifacts/` e local `.orion/artifacts/`.
* **Consequências:** Possibilidade de replay de auditoria, interceptação determinística pelo PEP e separação limpa entre a conversa rápida e planos técnicos densos.

---

### ADR-009: Dynamic Auto-Routing de Modelos por Complexidade & Ledger no CLI
* **Status:** Aprovado (24/10/2026)
* **Contexto:** O usuário precisa de controle financeiro visível e inteligência adaptativa de custos.
* **Decisão:** O ORION exibirá métricas de tokens e custos no CLI (estilo Claude Code). No gateway de modelos, oferecerá dois modos configuráveis por `/config` ou linguagem natural no chat:
  1. *Modo Automático (Dynamic Auto-Routing):* O ORION escala autonomamente para modelos de grande porte (Claude 3.7 Sonnet / Opus / Gemini Pro) em etapas de alto raciocínio/arquitetura, e retorna para modelos rápidos e eficientes (Gemini Flash / Qwen Coder) nas etapas de execução.
  2. *Modo Fixo:* O usuário define um modelo específico e imutável para toda a sessão.
  3. Suporte aberto a OpenRouter e provedores diretos.
* **Consequências:** Otimização agressiva de custos e máxima acurácia técnica sem intervenção manual contínua.
