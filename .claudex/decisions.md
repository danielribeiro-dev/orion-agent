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
* **Emenda (16/11/2026, ADR-046 [v0.5.3]):** o modo inicial passa a ser `auto` com faixas por reversibilidade; o modo supervisionado continua disponível como `ask`.

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

---

### ADR-010: Padrão Universal Agent Skills Standard (`SKILL.md`) com Progressive Disclosure
* **Status:** Aprovado (24/10/2026)
* **Contexto:** Agentes líderes (Claude Code, Antigravity, OpenHands, Microsoft) convergiram para um padrão modular aberto de habilidades para evitar injeção massiva de prompts no system prompt.
* **Decisão:** Adotar integralmente o padrão `SKILL.md` com YAML frontmatter (`name`, `description`, `compatibility`, `allowed-tools`) e subdiretórios opcionais (`scripts/`, `references/`, `assets/`). Implementar divulgação progressiva em 3 estágios: descoberta no boot com apenas nome e descrição (< 100 tokens/skill), ativação sob demanda (`use_skill`) e execução profunda com leitura de referências e execução de scripts dedicados.
* **Consequências:** Modularidade total, facilidade de compartilhamento com a comunidade e preservação máxima da janela de contexto.

---

### ADR-011: Dynamic Context Compactor & Branches Contextuais
* **Status:** Aprovado (24/10/2026)
* **Contexto:** Sessões longas de desenvolvimento degradam a qualidade da resposta do LLM e geram custos exorbitantes se todo o histórico de comandos for mantido continuamente no prompt.
* **Decisão:** Implementar o motor de compactação dinâmica com dois modos:
  1. *Auto-compaction silenciosa:* Ativada automaticamente ao atingir 80% do budget de contexto, sumarizando etapas passadas e purgando saídas intermediárias de ferramentas volumosas, enquanto preserva na íntegra os últimos 3 a 5 turnos (*vital tail*), caminhos de arquivos ativos e objetivos centrais.
  2. *Compactação manual:* Ativada via comando `/compact` (com suporte a diretrizes de foco).
  3. *Branches contextuais:* Tarefas de investigação operam em ramificações isoladas e, no `/merge`, geram síntese de checkpoint concisa (3 a 5 linhas) na Main Timeline.
* **Consequências:** Sessões potencialmente infinitas sem estouro de contexto ou perda de coerência operacional.

---

### ADR-012: Modelo de Embedding Local `bge-small-en-v1.5` & Fusão Híbrida RRF
* **Status:** Aprovado (24/10/2026)
* **Contexto:** Busca semântica local exige leveza, independência de bibliotecas gigantescas (como PyTorch) e precisão em terminologia de programação e infraestrutura.
* **Decisão:** Utilizar `fastembed` com o modelo `BAAI/bge-small-en-v1.5` (384 dimensões, ~130MB, execução local via ONNX Runtime em CPU). Aplicar limiar de deduplicação semântica de 0.92 e integrar com a busca BM25 do FTS5 através do algoritmo Reciprocal Rank Fusion (RRF, $k=60$) com teto rígido de injeção de contexto de 1.500 tokens.
* **Consequências:** Busca ultrarrápida (sub-50ms), funcionamento 100% offline e sem ruído de contexto no modelo principal.

---

### ADR-013: Prevenção de Memory Poisoning via Ciclo de Vida de Fatos & Tools Cognitivas
* **Status:** Aprovado (24/10/2026)
* **Contexto:** Agentes autônomos tendem a corromper sua própria memória de longo prazo ao gravarem suposições e hipóteses provisórias como verdades absolutas.
* **Decisão:** Estruturar a memória de fatos com enum de certeza `FactStatus` (`CONFIRMED`, `INFERRED`, `DEPRECATED`). Informações inferidas nunca sobrescrevem regras confirmadas pelo usuário. Expor 3 ferramentas cognitivas nativas no ReAct loop (`memorize`, `recall`, `deprecate_fact`) com registro de auditoria no PEP. Sincronizar em disco o arquivo curado `.orion/memory/MEMORY.md` com teto de 200 linhas.
* **Consequências:** Memória de longo prazo confiável, auditável pelo desenvolvedor e resistente a alucinações.

---

### ADR-014 [v0.4.0]: Comando Oficial `orion-agent` e Reserva de `orion` para eDEX/Desktop
* **Status:** Aprovado (24/10/2026); **emendado pelo ADR-033 (09/11/2026)**: `orion` e `orion-agent` ligam a mesma CLI
* **Contexto:** Distinção clara entre o binário CLI de alta velocidade para o dia a dia e futuras interfaces visuais cinematográficas.
* **Decisão:** O comando oficial para inicializar o CLI do agente no terminal é exclusivamente `orion-agent` (`[project.scripts] orion-agent = "orion.cli:main"`). O identificador `orion` fica formalmente reservado para a interface eDEX futurista / aplicativo desktop dedicado posterior.
* **Consequências:** Nomenclatura limpa, clareza operacional para o usuário e proteção de marca para futuros aplicativos gráficos da plataforma.

---

### ADR-015 [v0.4.0]: Stack Tecnológica do Stream CLI (`prompt_toolkit` + `Rich`)
* **Status:** Aprovado (24/10/2026)
* **Contexto:** Garantir máxima produtividade de digitação, rolagem nativa de terminal e realce de código sem o peso de TUIs fixas.
* **Decisão:** O Stream CLI do ORION utiliza exclusivamente:
  1. `prompt_toolkit` para o buffer de entrada na base, histórico persistente (`~/.orion/history`), autocomplete flutuante ao digitar `/`, expansão de caminhos de arquivo ao digitar `@` e atalhos readline/vi.
  2. `Rich` para o renderizador de streaming em Markdown (`Rich.Live`), banner adaptativo da Mão Cósmica com Buraco Negro, caixas de diálogo PEP e painéis de diff cirúrgico com sintaxe colorida (verde/vermelho).
  3. Fica expressamente descartada qualquer interface full-screen travada no CLI diário (como o eDEX original), preservando 100% da fluidez do trackpad/mouse do desenvolvedor.
* **Consequências:** Ergonomia impecável de desenvolvimento idêntica ao Claude Code e Antigravity, com tempo de inicialização sub-100ms e consumo mínimo de memória (< 30MB).

---

### ADR-016 [v0.4.0]: Catálogo Oficial de 20 Slash Commands (`/`) do O.R.I.O.N
* **Status:** Aprovado (24/10/2026)
* **Contexto:** Padronização dos comandos rápidos do terminal, combinando o melhor do mercado (Claude Code, Antigravity, Aider) e as inovações nativas do ORION.
* **Decisão:** Estabelecer o catálogo fechado de 20 comandos:
  - *Cognitivos:* `/plan`, `/goal`, `/grill-me`, `/review`
  - *Memória & Skills:* `/learn`, `/memory`, `/timeline`, `/recall`
  - *Contexto & Branches:* `/compact`, `/context`, `/branch`, `/merge`
  - *Operação & Governança:* `/diff`, `/undo`, `/run`, `/doctor`, `/cost`, `/config`, `/mcp`, `/voice`, `/clear`, `/help`
* **Consequências:** Zero comandos redundantes, máxima interoperabilidade mental para o desenvolvedor e recursos avançados de memória acessíveis com uma barra.

---

### ADR-017 [v0.3.0]: Command Trust Ledger & Autonomia Adaptativa (Capability Caching)
* **Status:** Aprovado (25/10/2026)
* **Contexto:** Desenvolvedores sofrem de fadiga de confirmação ao responderem `[Y/n]` dezenas de vezes para comandos inofensivos de rotina (como `npm test`, `pytest`, `cargo check` ou `sudo apt update`), o que no mercado leva à ativação perigosa de bypass total de segurança (o "YOLO Mode" do Claude Code).
* **Decisão:** Implementar o `CommandTrustLedger` no Policy Enforcement Point (PEP):
  1. Em modos `SUPERVISED` / `MANUAL`: O sistema continua exibindo confirmação `[Y/n]` interativa para ações modificadoras.
  2. Em modos `WORKSPACE_AUTO` / `ACCEPT_EDITS`: Mutações confinadas ao workspace autorizado não solicitam confirmação. Comandos de terminal consultam o cache seguro de assinaturas (`command_trust`). Se o comando já foi executado e aprovado anteriormente com sucesso (inclusive comandos com `sudo` benignos como `sudo apt install`), ele roda silenciosamente.
  3. Se for a primeira vez que um comando é executado pelo usuário, o sistema solicita a confirmação formal no primeiro uso e o grava no cache confiável.
* **Consequências:** Eliminação da fadiga de confirmação sem comprometer a segurança, tornando a experiência fluida e inteligente.
* **Emenda (16/11/2026, ADR-046 [v0.5.3]):** o ledger nunca foi instanciado em produção; passa a ser ligado na sessão e no daemon, com assinatura por prefixo normalizado e consultado no estágio 1 do classificador.

---

### ADR-018 [v0.3.0]: Nuclear Threshold & Popup Obrigatório de Senha do SO (Step-Up Authentication)
* **Status:** Aprovado (25/10/2026)
* **Contexto:** Comandos com raio de destruição catastrófico (exclusão em massa, formatação, `rm -rf`, modificações na raiz do SO `/` ou `~/.ssh`) não podem sob hipótese alguma ser executados de forma autônoma ou via simples confirmação de texto facilmente burlável. Além disso, no modo de presença ambiente por voz (v0.5.0), falas descuidadas ou conversas de fundo no quarto enquanto o usuário está deitado (*"apaga tudo e recomeça"*) poderiam disparar desastres.
* **Decisão:** Estabelecer a trava inviolável do **Nuclear Threshold**:
  1. Aplica-se incondicionalmente a **todos os modos de autonomia** (inclusive auto e accept-edits).
  2. Comandos que atingem o raio de destruição nuclear disparam obrigatoriamente um **popup nativo de autenticação do sistema operacional** (Polkit / `pkexec`, `zenity --password` ou `kdialog`), exigindo a senha ou biometria física do dispositivo.
  3. A regra é "popup em qualquer ambiente" (mesmo rodando em terminal gráfico X11/Wayland). Apenas na ausência estrita de servidor gráfico (sessão pura headless SSH sem display), faz fallback seguro solicitando senha mascarada no chat via `/dev/tty` (`getpass`).
  4. No modo de voz (v0.5.0), o ORION anuncia formalmente: *"Senhor, posso executar o comando destrutivo [detalhes]? Ele vai fazer X e Y. Por favor, autorize no dispositivo."* e aciona o popup na tela.
* **Consequências:** Blindagem física absoluta contra alucinações destrutivas, injeções de prompt e acidentes por áudio ambiente.
* **Emenda (16/11/2026, ADR-048 [v0.5.3]):** o popup não verificava a senha (qualquer texto valia). A presença passa a ser verificada por polkit, PAM do usuário ou fprintd; o nuclear se restringe ao irreversível que o ORION não consegue desfazer (ADR-046/047), e `sudo` comum usa askpass com verificação do próprio sudo.

---

### ADR-019: Gateway de Modelos com Foco em OpenRouter & Failover Local Leve (Qwen Coder 1.5B/3B)
* **Status:** Aprovado (25/10/2026)
* **Contexto:** Independência de provedores proprietários, otimização orçamentária e garantia de sobrevivência operacional mesmo em máquinas modestas sem placa de vídeo dedicada.
* **Decisão:**
  1. O Model Gateway da v0.3.0 adota o **OpenRouter** como provedor prioritário de primeira classe, fornecendo acesso a modelos de ponta (Claude 3.7 Sonnet, Gemini 2.5 Flash, Qwen 2.5 Coder 32B) através de uma única API key unificada, mantendo contratos abstratos (`BaseLLMProvider`) para provedores diretos futuros.
  2. O subsistema de resiliência offline **ORION Imortal** executa failover automático em menos de 2 segundos para o Ollama local utilizando a família leve **`qwen2.5-coder:1.5b`** ou **`qwen2.5-coder:3b`** (consumo estrito de 1.5GB a 2.8GB de RAM com quantização Q4_K_M).
* **Consequências:** Compatibilidade universal com hardware acessível sem travar a máquina do usuário e tolerância contínua a quedas de conexão.

---

### ADR-014 [v0.2.0]: A Arquitetura das 5 Esferas Cognitivas & Progressive Cognitive Unpacking (PCU)
* **Status:** Aprovado (25/10/2026)
* **Contexto:** Agentes convencionais sofrem de afogamento cognitivo (*Context Distraction*) ao injetar indiscriminadamente grandes blocos de texto no prompt de sistema a cada turno. Além disso, a memória do agente não separava perfil humano, regras de projeto e persona.
* **Decisão:** Estruturar a cognição do ORION em **5 Esferas Delimitadas**:
  1. `user_profile`: Nome, tratamento preferido (`"Senhor"`), matriz de maestria em ferramentas (`tool_mastery`) e canais remotos.
  2. `system_identity`: Origem Imutável (concebido por Daniel / `danielribeiro-dev`) + Persona Ativa (Jarvis, tom refinado, conciso em shell e didático em conceitos).
  3. `system_environment`: Telemetria de RAM, CPU, GPU e modo de vídeo.
  4. `project_decisions`: Base estruturada de ADRs com ciclo anti-envenenamento (`CONFIRMED`, `INFERRED`, `DEPRECATED`).
  5. `timeline_episodic`: Linha do tempo perpétua em SQLite WAL FTS5 BM25.
  - No boot, injeta-se apenas o **Cognitive Manifest** ultra-compacto ($< 250$ tokens). Detalhes são desempacotados sob demanda (*Progressive Cognitive Unpacking*) via ferramentas (`recall`, `inspect_environment`).
* **Consequências:** Zero afogamento de contexto, consumo mínimo de tokens e extrema precisão semântica.

---

### ADR-015 [v0.2.0]: Monitoramento Passivo de Telemetria do Host & Headroom Guard
* **Status:** Aprovado (25/10/2026)
* **Contexto:** Nenhum agente de mercado monitora o impacto físico das suas ações no hardware do usuário. Disparar navegadores pesados ou processamentos multimídia em computadores com pouca RAM causa congelamento total do sistema operacional.
* **Decisão:** Implementar o módulo passivo `EnvironmentMonitor` (via `psutil` com fallback para `/proc` do Linux) e a salvaguarda determinística **Headroom Guard**:
  - Se a memória RAM livre for inferior a $1.5\text{ GB}$, o agente bloqueia deterministicamente a abertura de instâncias de browser (Puppeteer/Chromium) ou geração de mídias pesadas, notificando o desenvolvedor e sugerindo alternativas leves (curl/API/texto).
* **Consequências:** Blindagem física contra travamentos do sistema operacional do desenvolvedor.

---

### ADR-016 [v0.2.0]: Escalonamento Remoto Out-of-Band (HITL via Telegram Bot com Inline Approval)
* **Status:** Aprovado (25/10/2026)
* **Contexto:** Tarefas longas em segundo plano que necessitam de aprovação de segurança PEP (LEVEL_2 ou LEVEL_3) ficam bloqueadas indefinidamente no terminal se o desenvolvedor se afasta da mesa para tomar um café ou atender outro compromisso.
* **Decisão:** Implementar o conector assíncrono de escalonamento remoto via **Telegram Bot**:
  - Se uma ação exigir aprovação e houver inatividade no terminal local superior a 180 segundos (configurável), o ORION despacha um alerta no Telegram do usuário com botões inline interativos `[Aprovar]` / `[Rejeitar]`.
  - Ao receber o callback autenticado do `telegram_chat_id` homologado, o PEP no PC libera a execução sem travar a máquina. Possui TTL de expiração de 10 minutos.
* **Consequências:** Alta autonomia real com supervisão humana contínua em qualquer lugar, sem que o desenvolvedor precise ficar acorrentado ao terminal.

---

### ADR-017 [v0.3.0] — Emenda de execução (v0.5.3 Sprint 1, 16/11/2026)
* Ledger ligado na sessão e no daemon (`~/.orion/command_trust.db`, protegido do agente). Aprende só o que o Senhor aprovou e terminou com exit 0; subagents nunca o recebem.
* Endurecido: comandos compostos (`;`, `&&`, `|`, redirecionamento, `$(...)` e crase até entre aspas) nunca são aprendidos nem consultados; a assinatura do git inclui todas as flags (`git push` ≠ `git push --force` ≠ `git push +main`); interpretadores (`python`, `bash`, `npx`, `make`, `docker`...) só casam o literal exato; `rm`, `mv`, `chmod`, `curl`, `sudo`, `systemctl` e git destrutivo nunca entram. Implementado em `CommandCanonicalizer.is_trustable`.

### ADR-017 [v0.4.0]: Desacoplamento do Cockpit Imersivo eDEX para a v0.7.0
* **Status:** Aprovado (26/10/2026) — registrado retroativamente em 06/11/2026.
* **Decisão:** O CLI `orion-agent` permanece 100% terminal; o cockpit sci-fi (Tauri v2 + WebGL, tokens do Figma) vira app standalone na v0.7.0. Ver `docs/design/TUI_DESIGN_SYSTEM.md`.
* **Nota:** o número 017 colide com o ADR-017 da v0.3.0 (Trust Ledger); desambiguado pelo sufixo de versão.

### ADR-018 [v0.4.0]: Paleta Oficial "Deep Cosmos & Glacial Platinum"
* **Status:** Aprovado (26/10/2026) — registrado retroativamente em 06/11/2026.
* **Decisão:** Paleta única do CLI com contraste WCAG AAA (> 13:1). Ver `docs/design/CLI_DESIGN_SYSTEM.md`.

---

### ADR-020: Provider Anthropic Nativo Antecipado para a v0.5.0
* **Status:** Aprovado (06/11/2026)
* **Contexto:** O ADR-019 e a spec da v1.6.0 adiavam o provider Anthropic nativo atrás de 8 gates (G1–G8) para não gastar tokens caros num agente imaturo. O Senhor decidiu tornar o ORION o seu agente principal de programação já na v0.5.0, o que exige Messages API nativa, `tool_use`, prompt caching e thinking.
* **Decisão:**
  1. A v0.5.0 ("Claude-Grade Agent") entrega o provider `AnthropicProvider` (`ANTHROPIC_API_KEY`), mantendo OpenRouter e Ollama como fallback via Circuit Breaker.
  2. Os gates G1–G8 deixam de bloquear **este escopo** (provider nativo, tool use estruturado, caching). O escopo "modo copiloto de código" e os demais itens da v1.6.0 permanecem futuros.
  3. G8 continua valendo na prática: nenhuma suíte paga roda sem opt-in explícito (`ORION_LIVE=1`) e sem teto de gasto.
  4. O motor agêntico continua sendo do ORION (nada de Agent SDK/Managed Agents).
* **Consequências:** O ORION passa a merecer o modelo por construção incremental: cada sprint da v0.5.0 é validada contra o provedor real. Voz e daemon de voz migram para a v0.6.0.

### ADR-021: Protocolo de Mensagens Estruturado (Content Blocks) no Lugar de `<tool_call>` em Texto
* **Status:** Aprovado (06/11/2026)
* **Contexto:** O protocolo textual (`<tool_call>` + regex) permite 1 tool por resposta, aceita JSON inválido como resposta final e força um prompt monolítico que impede prompt caching.
* **Decisão:** `LLMMessage.content` passa a aceitar blocos tipados (`text`, `thinking`, `tool_use`, `tool_result`, `image`); `LLMRequest` ganha `system`, `tools`, `tool_choice`, `thinking` e `cache_control`; toda tool declara `input_schema` validado; a conversa alterna assistant/user com `tool_result`. Todo `tool_use` continua passando pelo PEP. Providers legados recebem adaptador de compatibilidade.
* **Consequências:** Tools paralelas, cache de prefixo e validação de parâmetros; remoção de `TOOL_PROTOCOL`/`ToolCallFilter`.

### ADR-022: Daemon Event-Driven com Zero Tokens em Idle
* **Status:** Aprovado (06/11/2026)
* **Contexto:** A visão do ORION é ser um agente sempre presente (Jarvis) sem gastar tokens à toa.
* **Decisão:** O daemon (`systemd --user`) é determinístico por padrão: scheduler, watchers de arquivo/processo e cron não chamam LLM. O modelo só é acionado por gatilho, precedido de triagem barata (Haiku, `max_tokens` mínimo) quando aplicável. O ledger registra a origem de cada chamada (`user`, `daemon`, `cron`, `loop`, `subagent`). Ações agendadas nunca excedem o nível de autonomia configurado e ações nucleares sempre exigem step-up.
* **Consequências:** Em idle, zero chamadas ao provider (critério CA-10 da v0.5.0).

### ADR-023: Settings em Camadas, Regras de Permissão e Escalada com Pergunta
* **Status:** Aprovado (08/11/2026)
* **Contexto:** A configuração era um JSON plano lido ad hoc; "sempre permitir" vivia em RAM; sudo e caminhos fora do workspace eram bloqueios duros, o que impedia o ORION de fazer trabalho legítimo (`sudo apt update`) e dependia de listas que nunca cobrem todos os comandos perigosos.
* **Decisão:**
  1. `settings.json` em três camadas (`~/.orion/` < `<ws>/.orion/settings.json` < `<ws>/.orion/settings.local.json`); listas concatenam, escalares sobrescrevem. O `config.json` legado é lido e migrado sem ser apagado.
  2. Regras `allow`/`ask`/`deny` (`Tool(padrão)`), com **deny > ask > allow**. `allow` não casa comandos compostos (`;`, `&&`, `|`, redirecionamentos, substituições).
  3. **Confiança na primeira vez** (TOFU) para o `settings.json` do projeto: sem confiança, valem apenas `deny`, `ask`, `model` e `effort`; hooks, `allow`, `mode`, `mcp`, `env` e orçamento são ignorados. Confiança por hash do arquivo em `~/.orion/trusted_projects.json` (0600); qualquer mudança pede de novo.
  4. **Perguntar em vez de bloquear:** sudo (fora de `FULLY_AUTO`) e caminhos fora do workspace passam a **escalar** para uma confirmação de uso único, com o comando e o motivo na tela. Nunca viram "sempre permitir" (sudo), nunca são aprovados por regra ou hook, e **sem humano para responder** (`interactive=False`: hooks, subagents, jobs, daemon) são **negados**. Recusa devolve ao modelo o motivo e o pedido de alternativa.
  5. Seguem como bloqueio duro e inviolável: desafio nuclear do SO e safe-holding do circuit breaker.
  6. "Sempre permitir" grava regra `allow` exata na camada local quando expressável; o que não é (composto, glob, sem subject) vale só na sessão.
  7. Auditoria: `decision_source` (`mode|rule|ledger|user|user_escalation|hook`), negações por regra/escalada/hook registradas, `pending` fechado por `log_result`, e o `action_id` do engine propagado ao runtime (`CURRENT_ACTION_ID`).
* **Consequências:** Menos bloqueios arbitrários e mais decisão do Senhor, ao custo de mais perguntas (mitigado pelo comando exato na tela e por regras persistentes). Revoga o texto "sudo sempre negado em SUPERVISED/WORKSPACE_AUTO" do ADR-018 [v0.3.0].
* **Emenda (16/11/2026, ADR-046 [v0.5.3]):** caminhos fora do workspace deixam de escalar dentro do espaço do usuário; sem humano, escaladas vão para a Inbox em vez de serem negadas.

### ADR-024: Hooks que Só Bloqueiam
* **Status:** Aprovado (08/11/2026)
* **Decisão:** Oito eventos (`PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Stop`, `SessionStart`, `SessionEnd`, `PreCompact`, `Notification`). Hook é um comando shell com JSON do evento no stdin; **exit 2 bloqueia** (stderr volta ao modelo); qualquer outro código ou falha/timeout segue ao PEP. Um hook **nunca aprova** e nunca altera parâmetros. Roda antes do PEP em `LocalRuntimeProvider.execute`. Cada execução é auditada; a saída é tratada como dado não confiável (delimitadores `<<<ORION_` neutralizados, truncada).
* **Consequências:** Hooks não ampliam privilégio; o pior caso de um hook malicioso é código do usuário (daí a confiança TOFU para hooks de projeto).

### ADR-025: Comandos Custom e Plugin Mínimo
* **Status:** Aprovado (08/11/2026)
* **Decisão:** `.md` em `<ws>/.orion/commands` e `~/.orion/commands` viram slash commands (`$ARGUMENTS`, `$1..$9`); subpastas viram `/ns:cmd`; nomes nativos são reservados; projeto vence user. Plugin = pasta em `~/.orion/plugins/<nome>/` com `plugin.json` e `commands/`, `skills/`, `hooks.json`, `mcp.json`; comandos de plugin ganham namespace `/<plugin>:<cmd>`. Sem marketplace. O comando só envia o prompt ao agente; toda tool segue pelo PEP.
* **Consequências:** Afrouxa o "catálogo fechado" do ADR-016 [v0.4.0]: o catálogo oficial continua fechado e testado; os dinâmicos são aditivos e aparecem em `/help` e no autocompletar.

### ADR-026: MCP Completo — HTTP, OAuth Interativo Sob Demanda, Resources, Prompts e Reconexão
* **Status:** Aprovado (08/11/2026)
* **Decisão:**
  1. SDK `mcp>=2.3` (reescrita; clientes HTTP e `Auth` são `httpx2`) com `httpx2` declarado.
  2. OAuth só abre o navegador por pedido do Senhor (`/mcp auth`); no boot o fluxo é não interativo e sinaliza `auth_required`. Tokens em `~/.orion/mcp_auth/` (0700/0600, atômico), com `obtained_at` para recalcular a expiração depois de reiniciar.
  3. Cada conexão roda em uma task interna dedicada: o SDK cancela o escopo anyio do dono do transporte quando a conexão cai, e isso precisa ser lido como "queda", não matar o supervisor.
  4. Reconexão com backoff limitado só após ter conectado; falha inicial e login perdido não reconectam em loop.
  5. Conteúdo de resources e prompts de servidores remotos é dado não confiável.
* **Consequências:** o `refresh_mcp` da sessão passa a usar a geração do cliente; comandos dinâmicos (prompts MCP) usam `CommandRegistry.set_dynamic`.

### ADR-027: O ORION É a Segunda Metade do Senhor — Memória e Aprendizado como Virtude Central
* **Status:** Proposto (08/11/2026) — princípio fundacional aprovado pelo Senhor; mecanismos aguardam spec de versão
* **Princípio (frase do Senhor, preservar):** "A memória e a capacidade de APRENDER são uma das maiores virtudes do ORION." Ele não é um projeto que chama um LLM nem é limitado a um projeto: é uma segunda metade do Senhor que vive no computador (e, no futuro, o acompanha por outros dispositivos, se permitido). **Nada se perde, tudo se transforma:** a memória não acumula lixo, ela consolida, recicla e cria novas.
* **Decisão:**
  1. A memória é escopada por **pessoa/dispositivo**, não por projeto. Camadas: `global` (o Senhor), `organização/infra`, `projeto`, `dispositivo`. O projeto é um filtro de relevância, nunca a fronteira.
  2. O ORION aprende por **observação e instrução direta** (decisões, infra, preferências, nível de habilidade por domínio) e registra com proveniência (origem, data, confiança). Inferências nascem `PROVISÓRIAS` e só viram `CONFIRMADAS` por confirmação do Senhor ou evidência repetida (mantém a blindagem anti-envenenamento da v0.2.0).
  3. A higiene é cirúrgica: fatos duplicados se fundem, os superados são `DEPRECATED` com linhagem (substituído por X) e episódios antigos viram resumo. Nenhuma informação é apagada sem destino.
  4. A recuperação é **automática** (injeção em `<recalled_context>`, ADR-021/AutoRecall). As tools de memória são a gaveta de apoio, nunca o caminho principal.
  5. **Diretivas permanentes:** o Senhor pode ensinar reflexos em linguagem natural ("quando eu disser X, responda Y"). São determinísticas, zero token em idle (ADR-022) e passam pelo PEP quando mutam algo.
  6. **Skills por intenção:** skills próprias do Senhor ativam por intenção ("ative o protocolo babá"), sem `/skill-nome`. O `/` continua como atalho explícito.
  7. O formato de memória deve ser **portável** (exportar/importar, cifrado) para suportar multi-dispositivo na v3.0.0.
* **Consequências:** `IdentityManager` deve carregar este princípio (hoje em `src/orion/core/identity.py`, só alterável em sprint com spec). Monitorar terceiros (ex.: "protocolo babá") exige consentimento claro e vale apenas para contas/dispositivos do Senhor; ações nucleares seguem exigindo step-up.
* **Emenda (16/11/2026):** mecanismos especificados na v0.5.3 (ADR-050 memória, ADR-051 sessões e daily, ADR-046 escopo do usuário).

### ADR-028: Subagents — Privilégio Só Diminui, Sem Humano = Nega, Resultado por Referência
* **Status:** Aprovado (08/11/2026)
* **Contexto:** Subagents multiplicam custo (~4x a ~15x tokens) e risco; sistemas de mercado sofrem com filhos que herdam demais, rejeição que mata o filho e resultados perdidos na compactação do pai.
* **Decisão:**
  1. O filho roda com PEP próprio sob **teto do pai**: tools = interseção, modo = `min(pai, filho)`, `deny` e `ask` do pai unidos, `allow` nunca herdado, sem trust ledger, sem gravar regras. Nenhum caminho (agente custom, plugin, hook, schedule) ultrapassa o pai; ações nucleares seguem exigindo step-up.
  2. **Sem humano = nega:** `interactive=False` passa a negar **todo** `ask` (hoje só negava escalada). A negação devolve o motivo ao filho, que continua (não é morto).
  3. Profundidade padrão 1: o filho não recebe `task`, `ask_user`, `enter/exit_plan_mode`, `record_decision`, `memorize`, `deprecate_fact`. Concorrência, profundidade, turnos e tempo têm teto configurável; "sem limite" é proibido.
  4. O filho começa com contexto limpo (sem identidade, manifest, memória, skills ou MCP, salvo declarado); só o resumo curto volta ao pai. O completo fica em `~/.orion/agents/<id>/result.md` com `ref://`, sobrevivendo à compactação do pai. Resultado de filho é dado não confiável.
  5. Agente de projeto não confiável (TOFU, ADR-023) só pode **restringir**.
  6. O filho nunca altera o estado do circuit breaker do pai.
  7. (Implementação 6A) Sem humano, o desafio nuclear do SO **não abre**: o comando nuclear é negado. `cwd` de `run_command/glob/grep/search_files` é confinado ao escopo do filho.
* **Consequências:** Spec da Sprint 6 (6A). Auditoria e ledger ganham `agent_id`/`origin`.
* **Emenda (16/11/2026, ADR-046 [v0.5.3] Sprint 2):** o filho passa a herdar grants válidos do pai e a CONSULTAR o ledger do pai no estágio 1 do classificador (nunca aprende nele nem o recebe como seu). Presença no filho não vira pergunta: volta ao pai com o passo exato.

### ADR-029: Tasks em Loop de Thread Dedicada, com Portas Executor/TaskStore/Notifier
* **Status:** Aprovado (08/11/2026)
* **Contexto:** O REPL roda `asyncio.run` por turno e destrói o loop; tasks asyncio morrem entre turnos. A Sprint 7 trará o daemon.
* **Decisão:** A 6B roda subagents em background num **loop asyncio persistente em thread dedicada** (`ThreadExecutor`), com `copy_context`, fila thread-safe de notificações drenada antes de cada prompt e estado em SQLite (`~/.orion/tasks.db`, parametrizado). O runner depende só de `ExecutorPort`, `TaskStorePort`, `NotifierPort` e `WorkspacePort`: o daemon (Sprint 7), processos/sandbox (v1.5.0) e workers remotos entram como novos adaptadores sem reescrever o runner. `Ctrl+C` cancela o turno, não as tasks. Término chega por evento; zero token enquanto espera (ADR-022).
* **Consequências:** Eventos de agente usam um envelope JSON estável (`agent_id`, `parent_id`, `session_id`, `origin`), reaproveitável como payload do IPC da Sprint 7, do desktop (v0.7.0) e da voz (v0.6.0).

### ADR-030: Orçamento por Agente com Reserva Antecipada e Origem no Ledger
* **Status:** Aprovado (08/11/2026)
* **Contexto:** O `BudgetGuard` só tem teto diário global e checa antes de cada chamada (TOCTOU com chamadas paralelas); o ledger não distingue quem gastou.
* **Decisão:** `AgentBudget` (USD, tokens, turnos, tempo) por filho, `AggregateBudget` por chamada de `task`, mais o teto diário. Reserva antecipada (estimativa por `max_tokens` × preço do `CostCalculator`) antes de cada chamada. Estouro devolve resultado parcial marcado e retomável. O ledger ganha `origin` (`user|subagent|loop|cron|daemon`) e `agent_id` por migração `ALTER`; `task_id` mantém o significado atual. `/cost` e a status bar somam os filhos.
* **Consequências:** Critério de parada "custo agregado sem teto verificável" passa a ser testável.

### ADR-031: Núcleo de Agentes Agnóstico de Provedor (Tiers, Capacidades, Sem Downgrade Silencioso)
* **Status:** Aprovado (08/11/2026)
* **Contexto:** O ORION precisa durar além de qualquer provedor (Anthropic hoje; OpenRouter, Ollama e outros amanhã) e funcionar sem `ANTHROPIC_API_KEY`.
* **Decisão:**
  1. `agents/` depende apenas de portas (`LLMPort`, `ExecutorPort`, `TaskStorePort`, `NotifierPort`, `WorkspacePort`, `TriagePort`); nenhum campo de provedor (ex.: `cache_control`) vaza para ele. Cada provider declara *capability flags* (`supports_prompt_cache`, `supports_tool_use`, `context_window`, preço por Mtok) e decide como usá-los.
  2. Agentes declaram **tier** (`fast|balanced|heavy`) ou um *model profile* nomeado em settings; ID concreto de modelo é proibido por padrão (exige `allow_pinned_model`, só na camada do usuário). O router resolve `tier -> lista ordenada de candidatos` (`models.tiers`), com os padrões atuais.
  3. **Sem downgrade silencioso (CA-11):** agentes read-only podem cair para modelo local; agentes com tools mutantes exigem tier efetivo ≥ `balanced`; sem candidato adequado a task falha explicando. O modelo efetivo é gravado no registro e reutilizado na retomada.
  4. Formato do agente versionado (`schema_version`); leitor também aceita `.claude/agents/*.md`. `memory` é enum (`none|read|scoped:<escopo>`) para encaixar nos escopos da Memória Viva (ADR-027).
* **Consequências:** Trocar ou adicionar provedor não altera `agents/`; novos executores (daemon, remoto) e agentes auto-criados (v1.5.0) usam o mesmo contrato.

### ADR-032: Daemon Opt-in, IPC por Socket Unix e Roteador de Saída
* **Status:** Aprovado (09/11/2026)
* **Contexto:** A sessão vive e morre com a TUI; sem processo persistente não há agenda durável nem notificação com o terminal fechado. Mercado: Hermes usa um gateway único que embute o cron; Claude Code separa Routines, tarefas do Desktop e `/loop`; Antigravity centraliza aprovações num Inbox.
* **Decisão:**
  1. Um único daemon `systemd --user`, **desligado por padrão**. Níveis independentes: `install` (grava a unit), `enable` (sobe no login), `enable --boot` (exige `loginctl enable-linger` explícito). `disable` reverte tudo e preserva `~/.orion/`.
  2. Controle dentro da CLI: `/daemon start|stop|status|enable|disable` e tool `daemon_control` (conversa natural), sempre com confirmação do PEP.
  3. IPC JSON-RPC 2.0 em socket Unix `0600` em `$XDG_RUNTIME_DIR`, autenticação por `SO_PEERCRED`, sem TCP. Payload de eventos = `AgentEventEnvelope` (ADR-029).
  4. Roteador de saída por prioridade: cliente anexado, notificação nativa com ações, Telegram, e voz (v0.6.0). A notificação nativa é o canal garantido sem terminal e sem áudio.
  5. Idle = zero chamadas ao provider (ADR-022); `schedule_create` é nível confirmação; ação nuclear agendada nunca roda sem step-up local e não há aprovação nuclear remota.
* **Consequências:** `AgentSession` precisa de um `SessionSink` (`RichSink`/`IpcSink`) e de `status_bar`/`console` opcionais. Teto de custo por origem (`cron|daemon|loop`) no `BudgetGuard`.

### ADR-033: Emenda ao ADR-014 [v0.4.0] — `orion` e `orion-agent` ligam a mesma CLI
* **Status:** Aprovado (09/11/2026)
* **Contexto:** O ADR-014 reservava `orion` ao desktop. A spec da Sprint 7 usa `orion daemon ...`.
* **Decisão:** `orion` e `orion-agent` apontam para a mesma CLI. O desktop (v0.7.0) será um **app instalável como qualquer outro**, nunca iniciado por terminal, portanto não disputa o nome. Ligar o ORION automaticamente e deixá-lo sempre ativo é configurado dentro da CLI (`/daemon` ou conversa).
* **Consequências:** Atualizar `CLAUDE.md` e a documentação de comandos quando a emenda for aprovada.

### ADR-034: Aba Flutuante e Voz São Clientes do IPC do Daemon
* **Status:** Aprovado (09/11/2026)
* **Contexto:** O Senhor quer uma aba que se estende no hover, arrastável e recolhível, com mensagens, botões e pensamentos opcionais. No GNOME/Wayland não há layer-shell nem janela "sempre no topo" por aplicação.
* **Decisão:** A Sprint 7 entrega só o protocolo: stream de eventos, canal de pensamentos opt-in (`ui.show_thinking`, desligado por padrão), notificações com ação e Inbox de pendências. A aba e a voz são clientes do mesmo IPC, planejados para v0.6.0/v0.7.0 (ver `docs/planning/vision/ambient-panel-and-voice.md`).
* **Consequências:** Nenhuma UI gráfica na v0.5.0; o contrato do IPC precisa ser estável o bastante para esses clientes.

### ADR-035: Boot Escalonado e Dormência de Componentes por Pressão do Sistema
* **Status:** Aprovado (09/11/2026)
* **Contexto:** Em máquinas fracas, subir todos os componentes junto com o PC compete com o que o Senhor está fazendo. Máquinas fortes não precisam dessa cautela.
* **Decisão:**
  1. Sondagem de hardware sem LLM (RAM, núcleos, carga, PSI, bateria/tomada, disco) escolhe o perfil `minimal` (socket, scheduler, notificador), `standard` (acrescenta memória e MCPs sob demanda) ou `full` (tudo, inclusive embeddings). `daemon.boot_profile` aceita `auto` (padrão), `minimal` e `full`.
  2. O daemon espera a máquina estabilizar (carga e pressão abaixo do limiar), com teto de espera, em vez de usar atraso fixo.
  3. Um `PressureMonitor` determinístico observa a pressão, **descontando o consumo do próprio ORION**, e coloca em dormência os componentes `Sleepable` não essenciais. Usa limiares de entrada e de saída (histerese) e tempo mínimo por estado. Scheduler, IPC e auditoria são essenciais e nunca dormem.
  4. A unit systemd define `Nice`, `CPUWeight`, `IOWeight` e `MemoryHigh`. Limiares são calibrados por medição e configuráveis.
* **Consequências:** Componentes pesados (embeddings, MCPs, Telegram) precisam implementar `Sleepable` e carregar de forma preguiçosa. Zero token envolvido.

### ADR-036: Política de Presença Guiada por Memória
* **Status:** Aprovado (09/11/2026)
* **Contexto:** Preferências como "notícias de manhã" ou "manhã silenciosa" não podem ficar em código fixo; devem vir da memória e mudar com o Senhor (ADR-027).
* **Decisão:** O código oferece só mecanismos (janela de silêncio, teto de canal, resumo agrupado, briefing agendado). As regras vêm de fatos em `facts.db`, criadas por conversa (o modelo interpreta uma vez, o Senhor confirma) e avaliadas por um `PresencePolicy` determinístico antes de cada saída ou despertar. Janelas podem ser relativas ("primeira atividade do dia"). Só aprovação pendente e alertas críticos, conforme definido pelo Senhor, furam o silêncio. Sinais de feedback são registrados para a memória viva aprender depois.
* **Consequências:** Briefings que usam o modelo e a web entram no teto de custo por origem. Aprendizado automático de preferências fica fora da Sprint 7.

### ADR-037: Modelos Free, Cota Diária e Estado de Governança Protegido
* **Status:** Aprovado (09/11/2026)
* **Contexto:** A rodada manual com chave OpenRouter sem créditos (50 req/dia) mostrou: catálogo sem modelos `:free`; 429 de limite momentâneo e de cota diária tratados igual; o agente conseguiu gravar `~/.orion/web_allowlist.json` (ampliando a própria política); a auditoria não mostrava o step-up nuclear.
* **Decisão:** (1) Modelos `:free` entram no catálogo (custo 0, `ModelSpec.is_free`); `models.prefer_free` (padrão desligado) os põe à frente dos pagos por tier, no auto-routing e nos subagents, sem relaxar a regra de tools mutantes (tier >= balanced). (2) `RateLimitError.quota_exhausted` separa cota diária (não retenta, mensagem com hora de renovação) de limite momentâneo (retenta com backoff e honra `Retry-After`/`X-RateLimit-Reset` até 60 s). (3) O PEP nega a qualquer tool de escrita do agente os arquivos de governança de `~/.orion` (allowlist, settings, orçamento, chaves, auditoria, `secrets/`); só o Senhor os edita. Isto não cobre `run_command` com redirecionamento; a defesa nesse caso é o nível 3 e o modo. (4) A auditoria grava `decision_source=nuclear_stepup:<método>+<origem>` e `user_authorized=true` quando o desafio do SO autentica.
* **Consequências:** Free tem teto de 50 req/dia: testes automáticos continuam sem chamada paga ou free (`ORION_LIVE=1`). Falta um comando do Senhor para ampliar a allowlist sem editar o arquivo à mão (v0.5.1).
* **Emenda (16/11/2026, ADR-049 [v0.5.3]):** a allowlist da web vira blocklist do Senhor; o restante da proteção do estado de governança continua.


### ADR-038: MCPs de TUI como ferramenta de desenvolvimento (tui-mcp e ptywright)
* **Status:** Aprovado (10/11/2026)
* **Contexto:** Os testes de TUI usam `Console(file=StringIO)` e não enxergam cor, estilo ou layout real; descrever problemas visuais por texto é lento. Foram avaliados `tui-mcp` (PTY + xterm, PNG e texto) e `ptywright` (PTY + xterm, snapshot ANSI, asserções e goldens, roda sob Bun) contra o ORION real.
* **Decisão:** Instalar ambos no escopo de usuário do Claude Code, fora do repositório (`~/.local/share/claude-mcp/`). `tui-mcp` para avaliação visual e comparação com outras TUIs; `ptywright` como candidato a motor de regressão do futuro `tests/lab/`. São ferramentas de desenvolvimento: não entram no `pyproject.toml` nem no runtime do ORION. Nenhuma sessão de teste envia prompt a provedor pago ou free sem `ORION_LIVE=1`.
* **Consequências:** Guia operacional em `.claudex/tooling.md`. Riscos: projetos pequenos de um mantenedor só; o banner expõe a conta do GitHub mesmo com `HOME` isolado (teste não hermético) até existir `ORION_HOME`. O harness `tests/lab/` continua dependente de sprint própria.

### ADR-039: Identidade visual Horizon da TUI (v0.5.1)
* **Status:** Aprovado (11/11/2026).
* **Contexto:** Comparação com Claude Code e Hermes e testes no ORION real mostraram banner pesado (16 linhas, 6 badges), vão vazio entre banner e prompt (`dock_to_bottom`), menu cinza sem seleção, réguas claras demais e PEP sem hierarquia. O mock do Figma divergia do código e dos documentos.
* **Decisão:** (1) Mantém a paleta Deep Cosmos e o bloco Stellar. (2) Três tokens novos: `rule #566377`, `faint #7D8590`, `sel #1B2634` (contrastes medidos). (3) Banner lateral de 9 linhas, dica em três variantes por largura. (4) Remove `dock_to_bottom`. (5) Menu com seleção em fundo, categoria à direita e rodapé de atalhos. (6) Ferramentas com linha de resultado `›`. (7) PEP com moldura `pep_warn` e decisão registrada. (8) Status line com `% ctx` e estados `Ready/Working/Aguardando/Offline`. (9) Único glifo novo: `−` (U+2212) no diff. (10) Degradação para 256 cores e `NO_COLOR`.
* **Consequências:** Regra 3 de `CLI_AGENT_RULES.md` troca só a cor das réguas. Tema claro e skins por arquivo ficam fora. Mock no Figma pendente de cota do MCP (referência: `docs/design/horizon/`). A cadência de render (12 Hz) pode mudar se o perfil de CPU da Sprint 1 pedir; nesse caso, emendar aqui.

### ADR-040: A TUI não depende de CPR nem de rede
* **Status:** Aprovado (11/11/2026).
* **Contexto:** (a) O rodapé de status só aparece quando o terminal responde ao pedido de posição do cursor (CPR); sem resposta, some (V-06) e o prompt_toolkit imprime um aviso (V-05). (b) O primeiro envio baixa 67 MB do HuggingFace no meio do turno, com barras tqdm sobre a TUI (V-09): rede inesperada num agente soberano e econômico.
* **Decisão:** (1) O rodapé é desenhado sem depender de CPR e o aviso é suprimido. (2) O modelo de embeddings só é usado se já estiver em cache (`local_files_only`); sem cache, o recall cai no BM25 e avisa uma vez por sessão. (3) Baixar o modelo exige comando explícito do Senhor, com progresso pelo sink e sem tqdm; telemetria e barras do HF Hub desligadas. (4) Nenhum acesso à rede ocorre em teste de TUI.
* **Consequências:** Recall pode ser menos preciso até o Senhor instalar o modelo. Interação com a memória viva (ADR-027): o comando de instalação entra em `/doctor` ou `/memory`. Brain/Body preservado: o progresso passa pelo `SessionSink`.

### ADR-041: Harness de TUI em `tests/lab/` (pty + pyte, provider roteirizado)
* **Status:** Aprovado (11/11/2026). Complementa o ADR-038.
* **Contexto:** Os testes de TUI não enxergam cadência, teclas, cancelamento, menu nem rodapé; oito dos nove bugs novos só apareceram em movimento. A sonda de 11/11/2026 (pty + pyte, CPR respondido, amostragem de 20 ms, provider com streaming a ~200 car/s) os reproduziu sem custo.
* **Decisão:** Promover a sonda a `tests/lab/` com `pty_driver`, `ScriptedProvider` e `probes`, marcador `lab` opt-in, `HOME` temporário, `HF_HUB_OFFLINE=1`, chave de API falsa e baseline de métricas em `tests/lab/baseline.json` com gates relativos. `ptywright` e `tui-mcp` seguem como ferramentas de investigação e de golden de cor (ADR-038). `scripts/dogfood/` permanece para o modelo-ponte.
* **Consequências:** `pyte` entra no extra `dev`. O lab roda sob demanda (não faz parte dos ~20 s da suíte padrão). Nenhum teste automático chama provedor pago ou free; a rodada com modelo real é manual, `ORION_LIVE=1`, <= 15 req.

### ADR-042: Chaves em `~/.orion/.env` e segredos fora do alcance de leitura do agente
* **Status:** Aprovado (11/11/2026), pedido do Senhor.
* **Contexto:** O Senhor quer um `.env` para a chave do OpenRouter e futuras variáveis. Um `.env` no repositório viola "segredos nunca em arquivos versionados" e "runtime só em `~/.orion/`". O PEP só negava **escrita** em arquivos de governança: o agente podia **ler** uma chave com `read_file` e enviá-la ao provedor.
* **Decisão:** (1) `~/.orion/.env` (0600), criado com modelo comentado na primeira execução e nunca sobrescrito. (2) Precedência de cada chave: variável do shell, `.env`, arquivo legado `~/.orion/<nome>_api_key`. (3) O PEP nega ao agente **ler** (`read_file`, `grep`, `search_files`) e escrever `.env`, as chaves, `secrets/` e buscas a partir da raiz de `~/.orion`. (4) `/doctor` mostra a origem da chave e avisa permissão aberta, sem expor o valor.
* **Consequências:** `run_command` (ex.: `cat ~/.orion/.env`) continua possível com aprovação do Senhor (nível 3); a defesa é a revisão humana do comando. O `.env` de projetos do Senhor não é afetado.

### ADR-043: Renderizador em tela cheia como padrão, modo clássico como reserva [v0.5.2]
* **Status:** Aprovado (15/11/2026, com o plano da v0.5.2).
* **Contexto:** O modo inline (prompt entre turnos + `Rich.Live` transiente) não consegue manter o input vivo durante o turno, expandir um bloco no lugar, refazer a quebra ao redimensionar nem fixar o prompt embaixo (N-01 a N-05). O Claude Code adotou a tela alternativa como padrão em 2026, mantendo o renderizador clássico.
* **Decisão:** (1) Uma `Application` do prompt_toolkit em tela cheia, num loop asyncio único, com transcrição em células (estado recolhido por célula, linhas em cache por largura), input fixo embaixo, fila de pedidos, rolagem própria com auto-follow e overlays para PEP, perguntas e menus. (2) O `StreamRenderer` continua sendo o contrato: o `ScreenRenderer` herda dele e troca a escrita no terminal por células. (3) Modais (`modal.run_modal`) e saída de comandos (`console.print`) são redirecionados ao host da tela cheia quando ele está ativo. (4) Reserva: `ORION_TUI=classic`, `settings` `ui.tui`, `/tui`, terminal sem TTY ou `TERM=dumb`, e duas partidas falhas seguidas (`~/.orion/tui_state.json`). (5) Ao sair, a tela é restaurada e um resumo com o comando de retomada fica no scrollback.
* **Consequências:** A busca do terminal não vê a conversa: Ctrl+O abre a transcrição e `[` a despeja no scrollback. O mouse é capturado para rolar e expandir; `ORION_MOUSE=0` devolve a seleção nativa. O `attach` do daemon segue no modo clássico nesta versão.

### ADR-044: Instalação fora da venv, atualização e reversão [v0.5.2]
* **Status:** Aprovado (15/11/2026, com o plano da v0.5.2).
* **Contexto:** O `orion` só existe dentro de `.venv/bin`; sem ativar a venv o comando não roda. A regra Brain/Body reserva `~/.orion/` para runtime e dados, não para código.
* **Decisão:** (1) Código instalado em `~/.local/share/orion/versions/<versão>/` (venv própria por versão), symlink `current` e atalho `~/.local/bin/orion` (e `orion-agent`) que aponta para `current`. (2) `scripts/install.sh` instala a partir de um checkout (modo usuário) ou com `--dev` (editável, aponta para o repositório). (3) `orion update` busca tags `v*` do repositório de origem, instala a mais nova ao lado e troca o symlink de forma atômica; mantém as duas últimas versões; `orion update --rollback` volta à anterior. (4) Aplicar exige confirmação explícita no terminal (`--yes` só fora de TTY); o comando `orion update` executado pelo agente passa pelo PEP como ação nuclear. (5) Nenhuma verificação automática de rede: o Senhor roda o comando (ADR-040). (6) `/doctor` acusa atalho ausente no PATH e instalação duplicada.
* **Consequências:** Sem PyPI nem assinatura nesta versão: a confiança vem do repositório configurado. Dados do Senhor nunca são tocados pela instalação.

### ADR-045: Linguagem de movimento e orçamento de quadros [v0.5.2]
* **Status:** Aprovado (15/11/2026, com o plano da v0.5.2).
* **Contexto:** O pensamento é invisível, o spinner some durante o texto e a interface redesenha mesmo ociosa (N-06 a N-10, N-22 a N-24).
* **Decisão:** (1) Ocioso = 0 quadros. (2) Spinner a 12,5 quadros/s; 2 quadros/s quando o terminal informa perda de foco. (3) Redesenho limitado a 30 quadros/s, cada quadro dentro de synchronized output (`CSI ?2026h/l`; `ORION_SYNC_OUTPUT=0` desliga; desligado em `TERM=linux`). (4) Pensamento: linha viva `Pensando · 3,2s · 412 tok` com a última frase do raciocínio; ao terminar, bloco `▸ Raciocínio · 4,1s · 1,2k tok` recolhido, `▾` quando aberto; raciocínio com menos de 1 s e menos de 80 caracteres não vira bloco. (5) Durante o texto, `Escrevendo · 6,1s`. (6) Rodapé de turno `✔ 12,4s · 3 ferramentas · 2,1k tok · US$ 0,0050`. (7) Glifos novos `▸` e `▾`, só para blocos recolhíveis. (8) Título da aba (OSC 0), progresso indeterminado (OSC 9;4) durante o turno e sino ao terminar turno longo com a janela sem foco.
* **Consequências:** A tabela de glifos de `CLI_AGENT_RULES.md` ganha `▸ ▾`; `▼` deixa de existir. Valores PT-BR: vírgula decimal e `US$`.

### ADR-046: Governança v2 — o ORION mora no PC e presta contas [v0.5.3]
* **Status:** Aprovado (16/11/2026, com o plano da v0.5.3). Emenda os ADR-006, 017, 023 e 037.
* **Contexto:** O PEP decide por tool (LEVEL_0 a 3) e o escopo é o diretório onde o ORION abriu. No modo padrão, todo comando de terminal pergunta, o ledger do ADR-017 nunca foi ligado e escrever em outro repositório pede confirmação toda vez, sem "sempre". O ORION parece mais preso que Claude Code, Antigravity e Hermes, contrariando o ADR-027 ("vive no computador, não em um projeto"). Pesquisa e evidência: `docs/planning/versions/v0.5.3/pesquisa-memoria-e-autonomia.md`.
* **Decisão:**
  1. **Escopo = espaço do usuário** (`$HOME` e montagens do usuário). O workspace é filtro de relevância, não fronteira. Caminhos sensíveis (`~/.ssh`, `~/.gnupg`, rc do shell, units do usuário, governança do `~/.orion`) seguem protegidos.
  2. **Quatro faixas por raio de destruição e reversibilidade**, não por tool: `LIVRE` (leitura, web, escrita reversível no escopo, comandos de leitura), `CLASSIFICADA` (o resto), `PRESENÇA` (alto risco desfazível só com esforço), `NUCLEAR` (irreversível que o ORION não consegue desfazer). Mais uma **blocklist rígida** que nunca roda. Tool sem faixa declarada = `NUCLEAR` (deny by default).
  3. **Classificador em dois estágios** para a faixa Classificada: regras determinísticas + ledger primeiro; modelo FAST só para o que sobrar. O modelo é **cego ao raciocínio**: vê só as mensagens do Senhor e a chamada de tool, nunca saídas de tool nem texto do assistente. Sem modelo ou orçamento = `escalate`.
  4. **Modos** `plan`, `ask`, `auto` (padrão), `full` (sem estágio 2; Presença vira Classificada). `accept-edits` e `manual` são aliases. Nenhum modo toca Nuclear ou blocklist.
  5. Negação volta ao modelo com motivo; 3 negações seguidas ou 20 na sessão devolvem a decisão ao Senhor.
  6. **Sem humano** (daemon, jobs, subagent sem pai interativo): Presença e Nuclear viram pendência na Inbox/notificação, nunca execução e não mais negação seca.
  7. `CommandTrustLedger` instanciado; assinatura por prefixo normalizado.
* **Consequências:** Muito menos perguntas; a segurança passa a depender de três redes independentes (classificador, reversibilidade do ADR-047 e faixa Nuclear determinística), porque o classificador sozinho erra (~17% de falso negativo em ações exageradas no estudo da Anthropic). `test_security_audit.py` é reescrito para as faixas.
* **Registro de execução (Sprint 2, 16/11/2026):** (1) leitura que expõe chave ou credencial (`~/.ssh`, `~/.aws/credentials`...) e "leituras" que executam ou escrevem (`git -c`, `rg --pre`, `sed e/w`, `sort -o`, `env` sozinho) são Classificada, não Livre; (2) o modo `ask` continua perguntando comandos de leitura e `web_fetch`; `plan/auto/full` deixam leitura pura passar; (3) a faixa Nuclear decide o desafio do SO (`challenge_async(required=True)`), não mais os padrões antigos do `nuclear.py`; (4) regra `allow` não libera `sudo`; o classificador pode; (5) branch que não resolve conta como protegida; (6) o estágio 2 roda com origem `classifier` e teto padrão de US$ 0,20/dia, desligável por `ORION_CLASSIFIER_MODEL=0` (testes); (7) sem humano, o daemon recebe a pendência como item `alert` da Inbox e o job segue sem o passo (`ActionDeferred`).

### ADR-047: Motor de reversibilidade e aprovação por intenção [v0.5.3]
* **Status:** Aprovado (16/11/2026, com o plano da v0.5.3).
* **Contexto:** Pedir senha para ações desfazíveis é ritual repetitivo que o Senhor rejeitou. A maior parte do medo de `rm` é sobre arquivos não commitados.
* **Decisão:** (1) Antes de deleções e sobrescritas (`rm`, `mv` sobre existente, `>` sobre existente, `git reset --hard`, `git checkout -- .`, `git clean`), o PEP resolve os alvos e faz snapshot em `~/.orion/trash/<ts>-<id>/` (reflink, hardlink seguro ou cópia) ou `refs/orion/undo/<id>` no git; com snapshot, a ação é reversível e cai para Classificada. (2) Alvo que o parser não resolve sobe uma faixa. (3) Teto de 2 GiB por ação e 10 GiB no total, retenção de 7 dias; acima do teto, a ação sobe para Nuclear. (4) `/undo` e tool `undo_last` restauram. (5) **Aprovação por intenção:** um plano com passos de Presença pode ser aprovado uma vez, com escopo listado e TTL de 15 min; nunca cobre Nuclear nem blocklist.
* **Consequências:** Uso de disco controlado; limpeza do lixo por evento, nunca por relógio ocioso (ADR-022).
* **Registro de execução (Sprint 2, 16/11/2026):** (1) hardlink só na deleção e só com `st_nlink == 1` (com outro nome, uma escrita no lugar alteraria o snapshot); reflink por `FICLONE`, senão cópia; (2) sem motor de snapshot, ou com `sudo`, deleção é Nuclear; snapshot que falha nega a ação; (3) pastas regeneráveis (`node_modules`, `.venv`, caches, `build`) não são copiadas; acima do teto sobem para Presença ("recuperável de outra forma"); (4) `git clean` guarda o que `git clean -n` com as mesmas flags listaria; `/undo` de `reset --hard` reaplica o stash e avisa se o HEAD mudou, sem mover o ponteiro sozinho; (5) a restauração preserva a versão atual como `<nome>.orion-undo-<id>`; (6) grants vivem só na memória da sessão, casam comando por tokens iguais (ou prefixo explícito ` *`) e caminho por pasta resolvida.

### ADR-048: Presença verificada — askpass, chaveiro opt-in e polkit/PAM [v0.5.3]
* **Status:** Aprovado (16/11/2026, com o plano da v0.5.3). Emenda o ADR-018 [v0.3.0].
* **Contexto:** O popup nuclear aceita qualquer texto não vazio e descarta a senha; `run_command` roda sem terminal e sem askpass, então o `sudo` nunca consegue pedir senha. Por isso a senha real do Senhor "não era reconhecida".
* **Decisão:**
  1. **sudo:** `run_command` usa `sudo -A` com `SUDO_ASKPASS` apontando para um helper do ORION; quem verifica a senha é o próprio sudo. O pedido aparece num overlay mascarado (tela cheia) ou popup do SO.
  2. **Lembrar a senha (opt-in, `orion setup sudo`):** guardada só no chaveiro do SO (Secret Service), nunca em arquivo ou memória do ORION. O helper só preenche sozinho pedidos que o PEP marcou como não destrutivos; para Nuclear, recusa e exige presença. `--forget` apaga. Alternativa oferecida: `/etc/sudoers.d/orion` com NOPASSWD restrito a uma lista revisada pelo Senhor.
  3. **Nuclear:** polkit (`pkexec`, ação `org.orion.nuclear`), PAM do usuário com overlay mascarado, ou fprintd. Senha errada nega e é auditada. Fim do "qualquer texto vale". Nunca `/dev/tty` cru com a tela cheia ativa.
  4. A senha nunca passa pelo contexto do modelo, transcript, auditoria ou logs (estende o ADR-042).
  5. Presença por voz (v0.6.0) vale para a faixa Presença; Nuclear exige o dispositivo (mantém o espírito do ADR-018: fala de fundo não autoriza o irreversível).
* **Consequências:** Com o chaveiro ativo, a força da senha para `sudo` comum passa a ser a do classificador; por isso o preenchimento automático nunca cobre Nuclear e o Senhor pode preferir a lista do sudoers.
* **Registro de execução (Sprint 1, 16/11/2026):** (1) o broker do askpass só responde a quem o kernel mostra (SO_PEERCRED) ser filho do `sudo` do mesmo usuário, então o token sozinho não basta; (2) o preenchimento pelo chaveiro só vale na 1ª tentativa e só para `is_sudo_safe` (regras fixas até o classificador da Sprint 2); (3) a ação polkit própria `org.orion.nuclear` não foi instalada (exige root): usa-se `pkexec /bin/true` com aviso do comando na TUI; (4) presença verificada aceita dispensa o modal "y/n" do mesmo ato, salvo outra escalada (sudo, sensível) ou regra `ask`; (5) sudo em shell de segundo plano não tem askpass.

### ADR-049: Web aberta com blocklist e sessão contaminada [v0.5.3]
* **Status:** Aprovado (16/11/2026, com o plano da v0.5.3). Emenda o ADR-037 (item 3, quanto à allowlist).
* **Contexto:** `web_fetch` só abre 11 domínios e o agente não pode ampliar a lista; `web_search` raspa o DuckDuckGo e cai em anti-bot.
* **Decisão:** (1) `web_fetch` abre qualquer domínio público; a allowlist vira blocklist do Senhor (`/web block|unblock|list`). (2) Mantidos: bloqueio de IP privado em todo redirecionamento, tipos de texto, limites de tamanho e o princípio "conteúdo externo é dado, não instrução". (3) Depois de ler conteúdo externo, a sessão fica **contaminada** e o classificador endurece contra exfiltração (envio a host novo vira Presença). (4) `SearchProvider` em cadeia: Brave (`BRAVE_API_KEY`), `ddgs`, SearXNG (`settings.web.searxng_url`).
* **Consequências:** Mais superfície de injeção, contida pelo classificador cego às saídas de tool e pela sessão contaminada.

### ADR-050: Memória em cinco camadas, core congelado e Mordomo da Memória [v0.5.3]
* **Status:** Aprovado (16/11/2026, com o plano da v0.5.3). Implementa o ADR-027 e emenda os ADR-013 e 014 [v0.2.0] (manifesto).
* **Contexto:** Na rodada real, `facts.db` terminou vazio porque fatos só são gravados quando o modelo chama `memorize`; fatos confirmados só aparecem quando palavras do pedido batem; não há consolidação. Regex extrator é frágil; cutucar o modelo principal gasta o modelo caro e continua dependendo de obediência.
* **Decisão:**
  1. **Camadas:** core (sempre no system prompt, congelado por sessão, teto ~1.200 tokens: identidade, diretivas, CONFIRMED global e do projeto), trabalho (transcript + autocompact), episódica (cartões e rollups dia/semana/mês/ano), semântica (fatos com escopo, proveniência e tempo), procedural (skills).
  2. **Detector de saliência** determinístico decide **quando** olhar; não extrai.
  3. **Mordomo** em segundo plano (padrão sleep-time da Letta, operações da Mem0): recebe só o delta e os fatos vizinhos e devolve `ADD|UPDATE|SUPERSEDE|CONFIRM|NOOP`. Roda por saliência, a cada ~8 turnos, após 2 min ocioso com delta pendente, ou no fechamento. Modelo competente e barato (classe Haiku/Flash), sem downgrade silencioso para modelo fraco; teto diário `origin=memory`.
  4. **Regras no código, não no prompt:** pedido explícito do Senhor = CONFIRMED; inferência = PROVISIONAL; CONFIRMED nunca é sobrescrito por inferência (vira pergunta); 3 evidências em sessões distintas promovem; conteúdo de web/MCP nunca vira fato sobre o Senhor.
  5. Fatos **bitemporais** em SQLite (`valid_from/valid_to`, `supersedes`), sem banco de grafo. Nada é apagado: superado aponta para o sucessor.
  6. Recuperação do geral para o detalhe: core → auto-recall (FTS5 + vetores multilíngues em `sqlite-vec`) → `session_search` em cartões e rollups → transcript. `<recalled_context>` não é persistido no transcript.
  7. Transparência: linha `● aprendi: ... · desfazer` na TUI; "hoje aprendi" no cartão da daily; fila de revisão no `/memory`.
* **Consequências:** Memória independe do modelo principal; custo controlado pela frequência, não pela qualidade. O manifesto que só contava itens deixa o prompt.
* **Emenda (16/11/2026, antes da Sprint 1):** a crítica da spec mostrou que o desenho lembrava declarações, mas não trazia nada sem ser perguntado, não aprendia com comportamento e deixava o Mordomo confirmar a própria inferência. Acrescenta-se:
  8. **Evidência ancorada:** toda op cita ids presentes no delta (`user_msg`, `tool_obs`, `signal`), validados no código; fato sobre o Senhor só com `user_msg`; promoção a CONFIRMED conta falas do Senhor em 3 sessões distintas na tabela `fact_evidence`, nunca o que o modelo declara.
  9. **Observações locais:** leituras locais viram observações compactas e podem fundamentar fatos `project|device`; web e MCP nunca.
  10. **Sinais implícitos** (PEP, `/undo`, edição do Senhor sobre escrita do agente, reformulações, ritmo), determinísticos e locais, como evidência auxiliar.
  11. **Pendências proativas:** `commitments` com superfície no core da daily e na entrada de workspace, e prazo no scheduler; só lembram, nunca agem.
  12. **Perfil do Senhor:** síntese semanal de até 400 tokens no core (teto do core passa a 1.600), toda frase com fonte, editável e preservada.
  13. **Turnos indexados** em FTS5 (e vetores quando houver modelo), stemmer leve PT-BR sem modelo, e oferta única do modelo multilíngue na primeira sessão (o "s" do Senhor é a ação explícita do ADR-040).
  14. **Purge:** esquecer continua reversível; `purge` confirmado apaga de todos os índices.
  15. **Qualidade provada:** avaliação ao vivo opt-in da extração (precisão >= 0,90, recall >= 0,80, zero CONFIRMED indevido) é critério de fechamento da versão.

### ADR-051: Sessões indexadas, daily e threads [v0.5.3]
* **Status:** Aprovado (16/11/2026, com o plano da v0.5.3). Emenda o ADR-011 (branches persistidos).
* **Contexto:** Sessões são UUIDs sem título nem data, presas ao workspace; `/resume` não busca; o daemon troca de id a cada recarga; branches vivem em RAM. Uma daily única que cresce para sempre também não serve.
* **Decisão:** (1) `~/.orion/sessions.db` indexa sessões (tipo `daily|thread`, título, daily de origem, workspace opcional, cartão) com FTS5; JSONL segue como transcript. (2) Uma **daily por data local** (`daily-YYYY-MM-DD`), padrão do daemon e da voz sem TUI; virada às 04:00 ou na primeira atividade, fechando a anterior com cartão e abrindo a nova com resumo curto. (3) **Threads** filhas da daily: abertas pela TUI fora de `~`, por `/merge`, ou pelo próprio ORION com a tool `session_branch` quando um tópico se sustenta; `session_switch` volta a elas. (4) `/resume` busca por nome e data (`hoje`, `ontem`, `semana`, `mês`, `nov`, `2026-11`, `2026`, `16/11`) em árvore ano › mês › dia, global com filtro de workspace.
* **Consequências:** Migração idempotente dos JSONL com backup; a voz da v0.6.0 já nasce com sessão padrão e separação de assuntos.

### ADR-052: Núcleo enxuto — tools adiadas e cache de prompt [v0.5.3]
* **Status:** Aprovado (16/11/2026, com o plano da v0.5.3).
* **Contexto:** O primeiro "pong" custou 14.871 tokens de prompt (R-16), quase tudo schemas de tools.
* **Decisão:** (1) Só um núcleo de tools com schema completo; as demais aparecem por nome e uma linha, e `tool_search` carrega o schema sob demanda. (2) Ordem estável do prompt (preâmbulo → core congelado → instruções do projeto → tools) com marcadores de cache nos providers que suportam. (3) Meta: primeiro turno < 6k tokens, verificada em teste. (4) Subagent em 429 tenta outro modelo free do mesmo tier (R-17), sem baixar de tier.
* **Consequências:** Uma ida extra ao modelo quando uma tool adiada é usada pela primeira vez na sessão.
