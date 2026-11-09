# O.R.I.O.N — Governança e Policy Enforcement Point (PEP)
*(Operational Reasoning & Intelligence Orchestration Network)*

> Especificação do sistema determinístico de segurança, permissões e níveis de autonomia do O.R.I.O.N.

---

## 1. O Princípio de Deny by Default

O O.R.I.O.N opera sob o princípio de privilégio mínimo:
- Nenhum modelo de IA tem autorização intrínseca para executar comandos de terminal ou alterar arquivos no disco.
- Toda intenção de ação emitida pelo modelo no loop cognitivo (`Action`) é interceptada pelo **Policy Enforcement Point (PEP)** antes que qualquer rotina física de sistema seja executada no computador.

---

## 2. Níveis de Ação (Action Levels)

Cada ferramenta registrada no sistema possui uma classificação estática e determinística de risco:

| Nível | Categoria | Descrição | Comportamento Padrão |
| :--- | :--- | :--- | :--- |
| **LEVEL 0** | Informativo | Consulta de dados em memória, respostas de texto, raciocínio interno, emissão de artefatos. | Execução direta imediata. |
| **LEVEL 1** | Leitura Passiva | Leitura de arquivos locais (`read_file`), busca no repositório (`search_files`), status do sistema. | Execução direta com log de auditoria. |
| **LEVEL 2** | Mutação de Projeto | Criação de arquivo (`write_file`), edição cirúrgica (`edit_file`) restrita ao workspace atual. | Confirmação explícita no Modo Supervisionado (`[Y/n]`). |
| **LEVEL 3** | Crítico de Sistema | Comandos shell arbitrários (`run_command`), exclusão de arquivos, desligamento, alterações de rede. | Confirmação explícita com exibição do comando exato e impacto. |

---

## 3. Níveis de Autonomia Configuráveis

O usuário pode alternar o nível de autonomia do O.R.I.O.N via `/config` ou linguagem natural direta no chat:

1. **Modo Supervisionado (Padrão no MVP / v0.1.0):**
   - Ações de Nível 2 e 3 sempre exibem prompt de autorização `[Y/n]` no terminal antes de disparar.
2. **Modo Workspace Autônomo:**
   - Ações de Nível 2 dentro da pasta do projeto atual rodam sem confirmação. Ações de Nível 3 (fora do workspace ou comandos de shell) continuam exigindo confirmação humana.
3. **Modo Totalmente Autônomo (Com Limites Invioláveis):**
   - O agente executa planos de forma contínua, mas com travas invioláveis:
     - Impossível rodar comandos com `sudo` sem aprovação humana expressa.
     - Impossível alterar arquivos fora do diretório autorizado do usuário.
     - Impossível encerrar o próprio processo do O.R.I.O.N (*Self-kill protection*).

---

## 4. Auditoria e Rastreabilidade

Todas as ações sensíveis são gravadas de forma append-only no arquivo `~/.orion/audit.log`, contendo:
- `timestamp`: Momento exato em UTC/Local.
- `action_id`: UUID único do passo no Event Stream.
- `tool`: Nome da ferramenta acionada.
- `params`: Parâmetros enviados (caminho do arquivo, comando shell).
- `user_authorized`: Se houve confirmação humana explícita ou execução por política.
- `result_status`: Sucesso ou código de erro retornado.

---

## 5. Subagents: o teto do pai (v0.5.0 Sprint 6, ADR-028)

Um subagent roda com um PEP **próprio**, construído com `PolicyEnforcementPoint.for_subagent(pai, ...)`. Regra única: **privilégio só diminui**.

| Dimensão | Regra do filho |
| :--- | :--- |
| Modo de autonomia | `min(modo do pai AGORA, modo pedido)`; se o Senhor muda o modo do pai, o filho acompanha na hora. |
| Regras | `deny` e `ask` do pai valem no filho (vivas); `allow` do pai **nunca** é herdado; o filho nunca grava regra. |
| Humano | Nenhum. `interactive=False`: **todo** `ask` é negado, assim como escalada (sudo, fora do workspace) e o desafio nuclear do SO (nunca abre o prompt). A recusa volta ao filho como erro de tool e ele continua. |
| Trust Ledger | Não se aplica ao filho. |
| Plan mode / safe-holding | Herdados do pai, ao vivo. |
| Tools | Interseção do que o agente declara com o que o pai tem; nunca `task*`, `ask_user`, `send_message`, plan mode, `record_decision`, `memorize`, `deprecate_fact`, `todo_write`. MCP e memória só se declarados. |
| Workspace | O do pai ou, com `isolation: worktree`, um `git worktree` temporário: `cwd`/`path` de `run_command/glob/grep/search_files/read_file` precisam ficar dentro dele (caminhos relativos e `cwd` padrão partem da raiz do worktree). Fora de git, o isolamento **falha fechado**. |
| Projeto sem confiança | Agentes em `.orion/agents` só valem como escritos depois de `/agents trust` (hash do conjunto); antes, só leitura, tier ≤ balanced e orçamento nos padrões. |

Auditoria: todo registro de um filho carrega `agent_id`; o ledger de custos tem `origin` (`user|subagent|loop|cron|daemon`) e `agent_id`. Orçamento: reserva antecipada do pior caso em `AgentBudget → AggregateBudget → teto diário`, sem "ilimitado" (ADR-030).

