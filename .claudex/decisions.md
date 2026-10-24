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
* **Decisão:** Nenhuma ferramenta ou serviço proprietário (TalkCode, TalkAgent) será hardcodado no núcleo. Todas as integrações com sistemas externos, canais (WhatsApp, Telegram) ou agentes terceiros serão configuradas dinamicamente pelo usuário via Model Context Protocol (MCP), webhooks HTTP ou arquivos de configuração do usuário.
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
* **Decisão:** Adotar a arquitetura de Memória Tríplice:
  1. *Linha do tempo cronológica e busca exata:* SQLite com FTS5 (BM25).
  2. *Busca semântica conceitual:* ONNX / FastEmbed local (leve, sem PyTorch, 100% offline).
  3. *Fatos confirmados e perfil:* Armazenamento estruturado JSON/SQLite.
* **Consequências:** Alta velocidade, funcionamento offline, zero vazamento de dados e recuperação de contexto contextual precisa.

---

### ADR-005: Desacoplamento Progressivo do Hermes Agent
* **Status:** Aprovado (24/10/2026)
* **Contexto:** O Hermes Agent oferece ferramentas estáveis de I/O de terminal e arquivos, mas é um sistema monolítico alheio.
* **Decisão:** Encapsular o Hermes temporariamente atrás da interface `RuntimeProvider`. Gradualmente, substituí-lo por ferramentas nativas em Python e suporte ao Model Context Protocol (MCP).
* **Consequências:** Não reinventamos a roda na largada, mas mantemos controle total sobre a arquitetura do ORION para remover o Hermes no momento oportuno.

---

### ADR-006: Governança Progressiva (Modo Supervisionado Inicial)
* **Status:** Aprovado (24/10/2026)
* **Contexto:** Segurança e previsibilidade em execuções de ações reais no sistema operacional.
* **Decisão:** O ORION inicia em Modo Supervisionado, exigindo confirmação explícita `[Y/n]` do usuário para ações modificadoras (gravar arquivos, rodar comandos bash sensíveis, matar processos). No futuro, o usuário poderá customizar políticas de autonomia através de comandos como `/config`.
* **Consequências:** Prevenção contra danos ao ambiente de trabalho e total transparência operacional.

---

### ADR-007: Alinhamento Documental Prévio (Doc-First Engineering)
* **Status:** Aprovado (24/10/2026)
* **Contexto:** Evitar desenvolvimento caótico ou desalinhado entre o usuário e o assistente de IA.
* **Decisão:** Nenhuma linha de código executável em `src/` será escrita antes que todas as especificações arquiteturais, identidade visual (ASCII art) e o sistema de governança estejam aprovados.
* **Consequências:** Clareza absoluta de requisitos, ausência de retrabalho e rastreabilidade total.
