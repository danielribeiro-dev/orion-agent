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

### ADR-014: Comando Oficial `orion-agent` e Reserva de `orion` para eDEX/Desktop
* **Status:** Aprovado (24/10/2026)
* **Contexto:** Distinção clara entre o binário CLI de alta velocidade para o dia a dia e futuras interfaces visuais cinematográficas.
* **Decisão:** O comando oficial para inicializar o CLI do agente no terminal é exclusivamente `orion-agent` (`[project.scripts] orion-agent = "orion.cli:main"`). O identificador `orion` fica formalmente reservado para a interface eDEX futurista / aplicativo desktop dedicado posterior.
* **Consequências:** Nomenclatura limpa, clareza operacional para o usuário e proteção de marca para futuros aplicativos gráficos da plataforma.

---

### ADR-015: Stack Tecnológica do Stream CLI (`prompt_toolkit` + `Rich`)
* **Status:** Aprovado (24/10/2026)
* **Contexto:** Garantir máxima produtividade de digitação, rolagem nativa de terminal e realce de código sem o peso de TUIs fixas.
* **Decisão:** O Stream CLI do ORION utiliza exclusivamente:
  1. `prompt_toolkit` para o buffer de entrada na base, histórico persistente (`~/.orion/history`), autocomplete flutuante ao digitar `/`, expansão de caminhos de arquivo ao digitar `@` e atalhos readline/vi.
  2. `Rich` para o renderizador de streaming em Markdown (`Rich.Live`), banner adaptativo da Mão Cósmica com Buraco Negro, caixas de diálogo PEP e painéis de diff cirúrgico com sintaxe colorida (verde/vermelho).
  3. Fica expressamente descartada qualquer interface full-screen travada no CLI diário (como o eDEX original), preservando 100% da fluidez do trackpad/mouse do desenvolvedor.
* **Consequências:** Ergonomia impecável de desenvolvimento idêntica ao Claude Code e Antigravity, com tempo de inicialização sub-100ms e consumo mínimo de memória (< 30MB).

---

### ADR-016: Catálogo Oficial de 20 Slash Commands (`/`) do O.R.I.O.N
* **Status:** Aprovado (24/10/2026)
* **Contexto:** Padronização dos comandos rápidos do terminal, combinando o melhor do mercado (Claude Code, Antigravity, Aider) e as inovações nativas do ORION.
* **Decisão:** Estabelecer o catálogo fechado de 20 comandos:
  - *Cognitivos:* `/plan`, `/goal`, `/grill-me`, `/review`
  - *Memória & Skills:* `/learn`, `/memory`, `/timeline`, `/recall`
  - *Contexto & Branches:* `/compact`, `/context`, `/branch`, `/merge`
  - *Operação & Governança:* `/diff`, `/undo`, `/run`, `/doctor`, `/cost`, `/config`, `/mcp`, `/voice`, `/clear`, `/help`
* **Consequências:** Zero comandos redundantes, máxima interoperabilidade mental para o desenvolvedor e recursos avançados de memória acessíveis com uma barra.

---

### ADR-017: Command Trust Ledger & Autonomia Adaptativa (Capability Caching)
* **Status:** Aprovado (25/10/2026)
* **Contexto:** Desenvolvedores sofrem de fadiga de confirmação ao responderem `[Y/n]` dezenas de vezes para comandos inofensivos de rotina (como `npm test`, `pytest`, `cargo check` ou `sudo apt update`), o que no mercado leva à ativação perigosa de bypass total de segurança (o "YOLO Mode" do Claude Code).
* **Decisão:** Implementar o `CommandTrustLedger` no Policy Enforcement Point (PEP):
  1. Em modos `SUPERVISED` / `MANUAL`: O sistema continua exibindo confirmação `[Y/n]` interativa para ações modificadoras.
  2. Em modos `WORKSPACE_AUTO` / `ACCEPT_EDITS`: Mutações confinadas ao workspace autorizado não solicitam confirmação. Comandos de terminal consultam o cache seguro de assinaturas (`command_trust`). Se o comando já foi executado e aprovado anteriormente com sucesso (inclusive comandos com `sudo` benignos como `sudo apt install`), ele roda silenciosamente.
  3. Se for a primeira vez que um comando é executado pelo usuário, o sistema solicita a confirmação formal no primeiro uso e o grava no cache confiável.
* **Consequências:** Eliminação da fadiga de confirmação sem comprometer a segurança, tornando a experiência fluida e inteligente.

---

### ADR-018: Nuclear Threshold & Popup Obrigatório de Senha do SO (Step-Up Authentication)
* **Status:** Aprovado (25/10/2026)
* **Contexto:** Comandos com raio de destruição catastrófico (exclusão em massa, formatação, `rm -rf`, modificações na raiz do SO `/` ou `~/.ssh`) não podem sob hipótese alguma ser executados de forma autônoma ou via simples confirmação de texto facilmente burlável. Além disso, no modo de presença ambiente por voz (v0.5.0), falas descuidadas ou conversas de fundo no quarto enquanto o usuário está deitado (*"apaga tudo e recomeça"*) poderiam disparar desastres.
* **Decisão:** Estabelecer a trava inviolável do **Nuclear Threshold**:
  1. Aplica-se incondicionalmente a **todos os modos de autonomia** (inclusive auto e accept-edits).
  2. Comandos que atingem o raio de destruição nuclear disparam obrigatoriamente um **popup nativo de autenticação do sistema operacional** (Polkit / `pkexec`, `zenity --password` ou `kdialog`), exigindo a senha ou biometria física do dispositivo.
  3. A regra é "popup em qualquer ambiente" (mesmo rodando em terminal gráfico X11/Wayland). Apenas na ausência estrita de servidor gráfico (sessão pura headless SSH sem display), faz fallback seguro solicitando senha mascarada no chat via `/dev/tty` (`getpass`).
  4. No modo de voz (v0.5.0), o ORION anuncia formalmente: *"Senhor, posso executar o comando destrutivo [detalhes]? Ele vai fazer X e Y. Por favor, autorize no dispositivo."* e aciona o popup na tela.
* **Consequências:** Blindagem física absoluta contra alucinações destrutivas, injeções de prompt e acidentes por áudio ambiente.

---

### ADR-019: Gateway de Modelos com Foco em OpenRouter & Failover Local Leve (Qwen Coder 1.5B/3B)
* **Status:** Aprovado (25/10/2026)
* **Contexto:** Independência de provedores proprietários, otimização orçamentária e garantia de sobrevivência operacional mesmo em máquinas modestas sem placa de vídeo dedicada.
* **Decisão:**
  1. O Model Gateway da v0.3.0 adota o **OpenRouter** como provedor prioritário de primeira classe, fornecendo acesso a modelos de ponta (Claude 3.7 Sonnet, Gemini 2.5 Flash, Qwen 2.5 Coder 32B) através de uma única API key unificada, mantendo contratos abstratos (`BaseLLMProvider`) para provedores diretos futuros.
  2. O subsistema de resiliência offline **ORION Imortal** executa failover automático em menos de 2 segundos para o Ollama local utilizando a família leve **`qwen2.5-coder:1.5b`** ou **`qwen2.5-coder:3b`** (consumo estrito de 1.5GB a 2.8GB de RAM com quantização Q4_K_M).
* **Consequências:** Compatibilidade universal com hardware acessível sem travar a máquina do usuário e tolerância contínua a quedas de conexão.

---

### ADR-014: A Arquitetura das 5 Esferas Cognitivas & Progressive Cognitive Unpacking (PCU)
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

### ADR-015: Monitoramento Passivo de Telemetria do Host & Headroom Guard
* **Status:** Aprovado (25/10/2026)
* **Contexto:** Nenhum agente de mercado monitora o impacto físico das suas ações no hardware do usuário. Disparar navegadores pesados ou processamentos multimídia em computadores com pouca RAM causa congelamento total do sistema operacional.
* **Decisão:** Implementar o módulo passivo `EnvironmentMonitor` (via `psutil` com fallback para `/proc` do Linux) e a salvaguarda determinística **Headroom Guard**:
  - Se a memória RAM livre for inferior a $1.5\text{ GB}$, o agente bloqueia deterministicamente a abertura de instâncias de browser (Puppeteer/Chromium) ou geração de mídias pesadas, notificando o desenvolvedor e sugerindo alternativas leves (curl/API/texto).
* **Consequências:** Blindagem física contra travamentos do sistema operacional do desenvolvedor.

---

### ADR-016: Escalonamento Remoto Out-of-Band (HITL via Telegram Bot com Inline Approval)
* **Status:** Aprovado (25/10/2026)
* **Contexto:** Tarefas longas em segundo plano que necessitam de aprovação de segurança PEP (LEVEL_2 ou LEVEL_3) ficam bloqueadas indefinidamente no terminal se o desenvolvedor se afasta da mesa para tomar um café ou atender outro compromisso.
* **Decisão:** Implementar o conector assíncrono de escalonamento remoto via **Telegram Bot**:
  - Se uma ação exigir aprovação e houver inatividade no terminal local superior a 180 segundos (configurável), o ORION despacha um alerta no Telegram do usuário com botões inline interativos `[Aprovar]` / `[Rejeitar]`.
  - Ao receber o callback autenticado do `telegram_chat_id` homologado, o PEP no PC libera a execução sem travar a máquina. Possui TTL de expiração de 10 minutos.
* **Consequências:** Alta autonomia real com supervisão humana contínua em qualquer lugar, sem que o desenvolvedor precise ficar acorrentado ao terminal.
