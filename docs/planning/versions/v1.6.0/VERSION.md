# Spec — [v1.6.0] Native Model Providers & Code Copilot Mode

> **Atualização (2026-11-06, ADR-020):** o provedor Anthropic nativo (3.1), o tool use nativo (3.2), prompt caching e thinking foram **antecipados para a v0.5.0** por decisão do Senhor. Os gates abaixo deixam de bloquear esse escopo; continuam valendo para o modo copiloto de código e provedores adicionais.

> **Status:** 🧊 FUTURO / BACKLOG — Especificação preliminar, **NÃO iniciar antes dos Gates de Prontidão (seção 2)**  
> **Criada em:** 2026-11-06  
> **Concluída em:** —  
> **Autor(es):** Daniel Dev  
> **Branch:** `version/v1.6.0` (a criar somente quando os gates forem atingidos)  
> **Numeração:** provisória. Deve vir após a v1.5.0 (Self-Healing, Sandboxing e Subagentes Dinâmicos), pois a paridade agêntica depende deles.

---

## 1. Visão Geral & Motivação

### 1.1 Objetivo
Permitir que modelos de fronteira (**Claude** da Anthropic em primeiro lugar, depois outros) rodem **dentro do "corpo" do ORION** por provedores nativos e diretos, tornando o ORION o **copiloto de código principal** do Daniel, no lugar de agentes de terminal de terceiros.

Hoje o ORION já alcança Claude **indiretamente**, via OpenRouter (`gateway/registry.py` com `provider=OPENROUTER`). Esta versão troca o intermediário por integrações nativas, que dão acesso a recursos que o OpenRouter não repassa de forma fiel (prompt caching granular, thinking adaptativo, tool use nativo, fallbacks de recusa, contagem de tokens exata).

### 1.2 Por que NÃO agora (decisão registrada)
Plugar um modelo caro num agente de terminal ainda incompleto seria **prematuro e desperdício de tokens**. Um loop ReAct imaturo, sem tools robustas, sem memória e sem governança completa, queima tokens em erros, repetições e contexto mal gerenciado, sem entregar valor. O custo de errar é pago em dinheiro real a cada turno.

Princípio: **o agente precisa merecer o modelo.** Primeiro o ORION atinge paridade agêntica com o Claude Code e o supera em eficiência; só então ele recebe um modelo de fronteira como cérebro principal.

### 1.3 Anti-metas
- Não implementar nada disto durante as versões v0.4.0 a v1.5.0, a não ser que um gate seja antecipado por decisão explícita.
- Não depender de nenhum provedor único: o `BaseLLMProvider` continua agnóstico e o OpenRouter + Ollama seguem como fallback e modo offline (ORION Imortal).
- Não usar o Claude Agent SDK nem Managed Agents como motor: o loop agêntico é do ORION (princípio de soberania do núcleo).

---

## 2. Gates de Prontidão (critérios para iniciar)

Esta versão só começa quando **todos** os gates estiverem verdes, medidos em benchmark interno reproduzível (suíte de tarefas de código reais do próprio repositório):

| # | Gate | Critério mensurável |
| :--- | :--- | :--- |
| G1 | **Paridade agêntica** | Resolve, com modelo local/barato, um conjunto de tarefas de referência (editar multi-arquivo, depurar teste falhando, refatorar, navegar o repo) com taxa de sucesso comparável à do Claude Code com o mesmo modelo |
| G2 | **Tools de nível industrial** | Editor de código âncora + fallback AST, busca, shell com PEP e sandbox (v1.5.0), tool use paralelo e tratamento de erro de tool padronizado |
| G3 | **Subagentes e orquestração** | Subagentes dinâmicos estáveis (v1.5.0), com isolamento de contexto e retorno resumido |
| G4 | **Eficiência de tokens** | Uso de tokens por tarefa **menor** que o do Claude Code no mesmo benchmark (meta: ≥ 25% de redução), medido pelo Cost Ledger |
| G5 | **Memória e contexto** | PCU < 250 tok, compactação confiável, memória cross-sessão sem envenenamento, sem regressão de qualidade após compactação |
| G6 | **Governança completa** | PEP 0 a 3, Nuclear Step-Up Auth e auditoria em produção estável, sem bypass conhecido |
| G7 | **Estabilidade** | v1.0.0 em produção, cobertura ≥ 85%, zero falhas críticas abertas no loop ReAct |
| G8 | **Orçamento de teste** | Teto de gasto definido para a validação com API real (nunca rodar suíte de integração paga sem aprovação) |

---

## 3. Escopo Planejado

### 3.1 Provedor Nativo Anthropic (`gateway/providers/anthropic.py`)
- Implementa `BaseLLMProvider` (`complete` e `stream`) sobre o SDK oficial `anthropic` assíncrono.
- Autenticação por `ANTHROPIC_API_KEY` ou perfil OAuth (`ant auth login`), sem chave hardcoded.
- Mapeamento de erros do SDK para as exceções de domínio existentes (`RateLimitError`, `ProviderTimeoutError`, `ProviderConnectionError`, `ProviderAPIError`), alimentando o Circuit Breaker.
- Mapeamento de `usage` (incluindo `cache_read_input_tokens`, `cache_creation_input_tokens` e thinking) para `TokenUsage` e para o Cost Ledger.
- Modo de **fallback de recusa** do lado do servidor habilitado por padrão em modelos que o suportam.

### 3.2 Tool Use Nativo
- Substituir o parse textual de ReAct por blocos `tool_use` / `tool_result` nativos, com `strict: true` e schemas derivados das tools do ORION.
- Todo `tool_use` passa pelo **PEP** antes da execução; o modelo nunca executa nada diretamente.
- Execução paralela de tools independentes, com resultados devolvidos numa única mensagem.
- Atenção às restrições atuais de `tool_choice` forçado em modelos recentes (usar `auto` + instrução).

### 3.3 Eficiência de Tokens (diferencial do ORION)
- **Prompt caching** com prefixo estável (tools, depois system, depois mensagens), com conteúdo volátil sempre depois do último breakpoint; verificação de `cache_read_input_tokens` no ledger.
- **Thinking adaptativo** ligado ao esforço de raciocínio do status bar (`Alt+T`: HIGH, MED, LOW, OFF) via `output_config.effort`.
- **Auto-Routing por complexidade** mantido: tarefas FAST vão a modelo pequeno ou local; só HEAVY usa modelo de fronteira.
- Compactação do ORION integrada com a do servidor (blocos de compactação preservados, nunca descartados).
- Contagem prévia de tokens para o Budget Guard.

### 3.4 Modo Copiloto de Código
- Modo de sessão dedicado ao repositório atual: contexto de projeto via memória (`project_decisions`), `@` arquivos, diffs cirúrgicos e fluxo de revisão antes de aplicar.
- Comandos para trocar o "cérebro" em tempo real (`/model`) sem perder histórico.
- Relatório de custo por tarefa (não só por requisição), no Cost Ledger.

### 3.5 Catálogo de Modelos
- Atualizar `gateway/registry.py` e `router.py` com os modelos vigentes **na data do início da versão**. Os IDs e preços atuais devem ser reverificados na documentação oficial; não copiar valores desta spec.
- Os modelos `anthropic/claude-*-4-5` e `claude-haiku-3-5` do catálogo atual estão defasados e deprecações já anunciadas devem ser consideradas.

---

## 4. Riscos & Mitigações

| Risco | Mitigação |
| :--- | :--- |
| Gasto descontrolado em validação | Gate G8, Budget Guard diário e testes com SDK mockado por padrão |
| Acoplamento a um fornecedor | Interface `BaseLLMProvider` preservada; testes de contrato por provedor |
| Mudanças de API do SDK | Fixar versão, ler a doc oficial no início da versão, testes de contrato |
| Prompt injection via tool results | PEP + delimitação estrita de prompts + conteúdo de tools tratado como dado |
| Regressão do modo offline | Suíte de failover (Ollama) obrigatória no CI desta versão |

---

## 5. Sprints (rascunho, a detalhar quando os gates forem atingidos)

| Sprint | Tema |
| :--- | :--- |
| 1 | Provedor Anthropic nativo + mapeamento de erros/usage + testes de contrato |
| 2 | Prompt caching, thinking adaptativo e integração com Cost Ledger/Budget Guard |
| 3 | Tool use nativo atrás do PEP, com execução paralela |
| 4 | Modo Copiloto de Código, `/model` ao vivo e relatório de custo por tarefa |
| 5 | Benchmark final vs. Claude Code, tuning de esforço e fallbacks |

---

## 6. Definition of Done
- Todos os gates G1 a G8 documentados como atingidos antes do início.
- Cobertura global ≥ 85%; suíte offline/failover verde.
- Benchmark comprovando eficiência de tokens superior (G4) com o provedor nativo.
- ROADMAP atualizado e esta spec movida de "Futuro" para "Em execução".
