# Estudo — Subagents, Tasks e Economia de Tokens (base da Sprint 6)

> Data: 2026-11-08. Pesquisa comparativa para a Sprint 6 da v0.5.0. Fontes oficiais quando possível; onde só houve fonte secundária está marcado **[verificar]**. Percentuais de blogs não devem virar meta sem medição própria.

## 1. Síntese

Sistemas maduros convergem em: contexto isolado do filho, retorno só do resumo, limites de concorrência e profundidade, herança de permissão do pai e economia por cache de prefixo. As dores reais são custo opaco, perda de resultado na compactação, isolamento que cai em silêncio e filhos que herdam demais. O ORION pode fazer melhor com **teto no código, orçamento em USD por agente, falha fechada e resultado por referência**, tudo atrás de portas agnósticas de provedor.

## 2. Sistemas

### Claude Code (https://code.claude.com/docs/en/sub-agents, /agent-teams, /costs, /prompt-caching, /scheduled-tasks)
- Subagents em `.md` com frontmatter (`tools`, `disallowedTools`, `model`, `permissionMode`, `maxTurns`, `isolation: worktree`, `skills`, `hooks`...). Filho começa limpo; só o prompt do pai chega. Retorna a mensagem final.
- Built-ins: Explore (leitura), Plan, general-purpose. Background por padrão; limite de 20 concorrentes e profundidade 3; `max_budget_usd` no SDK.
- Teams (experimental): ~7x tokens; `/resume` não restaura teammates; sobrescrita de arquivos; herdam o modo do lead, inclusive bypass.
- Monitor (eventos) é mais econômico que polling; `/loop` só vive com a sessão aberta e expira em 7 dias.
- Cache: prefixo exato; nada dinâmico no system; não mudar ferramentas nem modelo no meio da sessão (troca de modelo só via subagent); compactação por fork cache-safe.
- Dores (via espelho `claudeissues.com` **[verificar]**): compactação descarta resultado de filho concluído (#32099); rejeição mata o filho (#4587); instruções do usuário não chegam ao filho (#5833); modelo fixado perdido ao retomar; filhos lançados sem pedido.

### Codex CLI (https://learn.chatgpt.com/docs/agent-configuration/subagents)
- Filho herda sandbox e política de aprovação; o TOML custom **não** pode sobrescrevê-los. Sem humano, ação que pede aprovação falha. Admite que subagents gastam mais que agente único.

### Gemini CLI (https://geminicli.com/docs/core/subagents/)
- `.gemini/agents/*.md`; sem aninhamento; `max_turns` (30) e `timeout_mins` (10) por agente; política mira o subagent.

### Anthropic Engineering
- Multi-agente: ~4x (agente) e ~15x (multi) tokens; tokens explicam ~80% da variância; "a maioria das tarefas de código" não se beneficia (https://www.anthropic.com/engineering/multi-agent-research-system).
- Regras de escala de esforço embutidas (primeiras versões criavam 50 subagents para consulta simples). Handoff com objetivo, formato, ferramentas e limites; saída em armazenamento externo com referência leve.
- Contexto: menor conjunto de tokens de alto sinal; limpar resultados antigos de ferramentas; notas persistentes; subagent devolve 1–2 mil tokens (https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents). Ferramentas: truncar com orientação, `concise|detailed`, erros acionáveis (https://www.anthropic.com/engineering/writing-tools-for-agents). Comece simples (https://www.anthropic.com/engineering/building-effective-agents).

### Hermes Agent (Nous Research) (https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation, /memory)
- `delegate_task` (goal, context, tasks em lote, output_schema, role leaf/orchestrator); padrão 3 concorrentes; filhos leaf sem delegate/memory/send/cron; profundidade 1; worktree opcional (cai em silêncio para workspace compartilhado); filhos herdam credenciais do pai; só o resumo volta, transcript por task.
- Memória: arquivos pequenos com teto; snapshot congelado no prompt (preserva cache); skills criadas pelo agente.

### Google Antigravity **[verificar: sem acesso à doc oficial]**
- Agent Manager + Artifacts (plano, walkthrough, screenshots). Dores: cotas opacas, bloqueios, instabilidade, lock-in.

### Outros **[verificar]**
- Roo Code (orquestrador sem efeitos colaterais; subtarefa herda só o `message`; queixa de contexto escondido), Letta (sleep-time compute; experimental), mem0 (operações sobre fatos), OpenClaw (heartbeat com LLM custa fixo e pode fugir do controle), Aider (repo map com orçamento fixo), OpenHands (microagents por palavra-chave, sandbox).

## 3. Lacunas de pesquisa
Documentação oficial de Antigravity, Aider, OpenHands, Cursor, Devin e LangGraph; detalhes de operações do mem0; algoritmo de criação de skills do Hermes.

## 4. Lições adotadas na spec

| # | Lição | Onde entra |
| :--- | :--- | :--- |
| 1 | Subagent isola contexto volumoso; não paralelizar por padrão | Princípio 1; descrição do agente e regras de escala no prompt do `task` |
| 2 | Tetos no código | `agents.max_concurrent/max_depth`, `max_turns`, `timeout_s`, `budget_usd` |
| 3 | Privilégio só diminui; sem humano nega | ADR-028; `ceiling` no PEP |
| 4 | Cache de prefixo; modelo só muda via subagent | Prefixo estável do filho; `model_used` gravado |
| 5 | Handoff explícito e resultado por referência | `goal/context/output_schema`; `ref://` em `~/.orion/agents/` |
| 6 | Eventos, não polling | Fila de notificações (6B), zero token enquanto espera |
| 7 | Medir por agente | `origin`/`agent_id` no ledger e na auditoria |
| 8 | Falhar fechado | Worktree e tier mutante (ADR-031) |
| 9 | Rejeição não mata o filho; correções chegam a ele | Rejeição devolve erro ao filho; `send_message` |
| 10 | Provedor é detalhe | Portas e *capability flags* (ADR-031) |

## 5. Armadilhas a evitar
Heartbeat com LLM; fan-out aninhado sem teto; filhos com credenciais ou escrita de memória; queda silenciosa para menos isolamento; memória sem teto injetada a cada turno; consolidação sem auditoria; aprender a partir de conteúdo não confiável; cota opaca; confiar em percentuais de blog; esconder do usuário o que o filho recebeu e devolveu.
