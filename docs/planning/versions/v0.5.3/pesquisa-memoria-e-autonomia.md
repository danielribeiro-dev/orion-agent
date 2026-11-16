# Pesquisa — Memória e Autonomia (base da v0.5.3)

> **Data:** 16/11/2026 · **Autor(es):** Daniel Dev & Claude · **Uso:** fundamenta os ADR-046 a 052.
> Números de benchmark citados aqui são, em sua maioria, publicados pelos próprios fornecedores e não foram reproduzidos de forma independente. Configurações (modelo, juiz, orçamento de tokens) diferem entre eles; não servem como ranking.

---

## 1. Diagnóstico do código (16/11/2026)

### 1.1 Memória
| # | Achado | Evidência |
|:--|:--|:--|
| M-01 | Fato só é gravado se o modelo chamar `memorize`; a rodada real terminou com `facts.db` vazio (R-06) | `runtime/local_provider.py:110-114`, `core/identity.py:110-111` |
| M-02 | Fatos CONFIRMED só entram no prompt se palavras do pedido baterem por substring; identidade e "Senhor" nunca ficam sempre presentes (R-06, R-07) | `memory/auto_recall.py:149-171` |
| M-03 | Sem consolidação, fusão, resumo de sessão ou de dia; `day_markers.summary` nunca é preenchido | `memory/timeline.py`, `update_day_marker_summary` sem chamador |
| M-04 | Manifesto só conta itens e mostra sempre `0 events | LAST: never` | `tui/session.py:728-740`, `memory/manifest.py` |
| M-05 | Embedding `bge-small-en-v1.5` (só inglês) em conversa PT-BR | `memory/vector_store.py:33-103` |
| M-06 | Busca vetorial lê a tabela inteira a cada adição e busca | `memory/vector_store.py:270-312` |
| M-07 | `<recalled_context>` é salvo no transcript e reinjetado ao retomar | `core/engine.py:320-321` |
| M-08 | Sessões são UUID sem título nem data, presas ao workspace; `/resume` sem busca e lê todos os JSONL | `tui/session.py:265`, `sessions/store.py:142-166`, `tui/commands/session.py:13-36` |
| M-09 | Não existe daily; o daemon troca de UUID a cada recarga | `daemon/app.py:268-272,483-496` |
| M-10 | Branches só em RAM; checkpoints guardam `answer[:200]` | `timeline/branch_manager.py`, `tui/session.py:1464` |
| M-11 | Categorias de fato fixas em quatro; `FactsStore` usa hora sem fuso | `memory/models.py:146`, `memory/facts_store.py` |
| M-12 | `/context` conta o preâmbulo duas vezes | `tui/session.py:1603-1612` |

### 1.2 Governança
| # | Achado | Evidência |
|:--|:--|:--|
| G-01 | O popup nuclear aceita qualquer texto não vazio e descarta a senha; não há PAM, polkit nem hash | `governance/nuclear.py:402-404,419-421,478-484` |
| G-02 | `run_command` roda com `start_new_session=True`, sem TTY e sem askpass: `sudo` nunca consegue pedir senha | `runtime/tools/run_command.py:100-108`, `runtime/shells.py:66` |
| G-03 | O fallback por `/dev/tty` disputa o terminal com a tela cheia (ADR-043) | `governance/pep.py:694`, `nuclear.py:453-471` |
| G-04 | LEVEL_3 sempre pergunta no modo padrão (accept-edits) | `governance/pep.py:844-847` |
| G-05 | `CommandTrustLedger` (ADR-017) nunca é instanciado | `tui/session.py:323-327` |
| G-06 | Escrita fora do cwd escala sempre, sem "sempre", e é negada sem humano; `add_root` sem chamador | `pep.py:772-805`, `tui/modal.py:245-246`, `permissions.py:189` |
| G-07 | Leitura fora do cwd já é livre (teste `test_sec_read_file_outside_workspace_allowed`); recusas são do modelo | `runtime/tools/read_file.py:111-122` |
| G-08 | `web_fetch` só abre 11 domínios; o agente não pode ampliar a lista e não há comando para isso | `runtime/web_policy.py:21-33,91-95` |
| G-09 | `web_search` raspa `html.duckduckgo.com` e cai em anti-bot (HTTP 202 / anomaly) | `runtime/tools/web_search.py:96-101` |
| G-10 | Sem humano (daemon, subagent, job), toda escalada é negada em vez de ir à Inbox | `pep.py:670-685,792-805` |

---

## 2. Memória: o que o mercado faz

| Sistema | Ideia central | O que aproveitamos | O que evitamos |
|:--|:--|:--|:--|
| **Letta (MemGPT)** | Hierarquia tipo SO: blocos *core* sempre no contexto, *recall* pesquisável, *archival*. Agente de sono (*sleep-time*) edita os blocos em segundo plano | Bloco core sempre presente; consolidação fora do turno | Servidor dedicado; o próprio agente principal gerenciando memória (deixa o turno lento, problema que a Letta atribui ao MemGPT original) |
| **Hermes Agent (Nous)** | `MEMORY.md` (~800 tok) e `USER.md` (~500 tok) congelados no system prompt no início da sessão para preservar o cache; tool `memory` com add/patch/remove; `session_search` FTS5 sem LLM; revisão a cada ~10 turnos | Snapshot congelado por sessão; `session_search` sem LLM com rolagem; teto rígido no core | Cutucar o modelo principal para salvar (gasta o modelo caro e continua dependendo de obediência) |
| **Mastra Observational Memory** | Observer comprime a conversa em notas datadas e priorizadas; Reflector funde e descarta o superado ao passar de um limiar. 84,23% (gpt-4o) e 94,87% (gpt-5-mini) no LongMemEval-S, números da Mastra | Duas fases (observar → refletir); notas com data; janela estável que só invalida o cache na reflexão | Observer síncrono que bloqueia a conversa |
| **Mem0** | Pipeline extração → atualização: um LLM extrai fatos de cada par de mensagens e decide ADD/UPDATE/DELETE/NOOP contra os vizinhos. Afirma 94,4 no LongMemEval (fonte: Mem0) | Operações estruturadas contra fatos vizinhos | Rodar extração a cada mensagem (custo) |
| **Zep / Graphiti** | Grafo de conhecimento temporal: episódios, entidades/fatos, comunidades; validade no tempo. 71,2 no LongMemEval (gpt-4o, segundo a página da Mem0) | Fatos bitemporais (`valid_from/valid_to`) e linhagem | Banco de grafo como infraestrutura obrigatória ("Does Memory Need Graphs?", 2026, questiona o ganho) |

**Conclusões para o ORION**
1. O que falha hoje não é a busca, é a **escrita** (M-01) e a **presença garantida** (M-02). Recuperação sofisticada sobre um banco vazio não resolve nada.
2. Extração precisa de um modelo **competente**: um fato errado gravado como verdade envenena todas as sessões seguintes. Economizar aqui é o "barato que sai caro". Economiza-se na **frequência** (detector de saliência, lote, delta), não na qualidade.
3. SQLite + FTS5 + vetores + campos temporais entregam o essencial do grafo temporal sem nova infraestrutura.
4. O core deve ser **congelado por sessão** (cache de prompt) e o que é aprendido durante a sessão já está no contexto de qualquer forma.
5. Busca episódica do geral para o detalhe (cartões e rollups → transcript) é mais barata e precisa que embeddings sobre todos os turnos.

---

## 3. Autonomia: o que o mercado faz

| Sistema | Modelo de permissão | Lição |
|:--|:--|:--|
| **Claude Code auto mode** | Três tiers: leitura e regras do usuário sem classificador; escrita no projeto sem classificador; o resto (shell, web, fora do projeto, subagents) passa por um classificador. O classificador é **cego ao raciocínio**: vê só mensagens do usuário e chamadas de tool, nunca saídas de tool (corta injeção). Dois estágios: filtro rápido "na dúvida, bloqueie" e reavaliação com raciocínio só quando o filtro marca. Negação volta ao agente com motivo; 3 negações seguidas ou 20 no total devolvem ao humano. Ao entrar no modo, regras amplas de execução arbitrária são descartadas. Taxas publicadas: 0,4% de falso positivo no tráfego real e 17% de falso negativo em ações exageradas reais | O classificador é o caminho certo para "autônomo sem ser YOLO", mas falha em ~1 de 6 ações exageradas: precisa de uma rede de segurança que não dependa dele (reversibilidade + último nível determinístico) |
| **Hermes Agent** | `approvals.mode`: `smart` (padrão, LLM auxiliar aprova o baixo risco, nega o perigoso, pergunta o incerto), `manual`, `off`/`--yolo`. Blocklist rígida que nem o YOLO fura. Aprovação "sempre" vira allowlist persistente. Container é tratado como fronteira | Blocklist rígida separada do classificador; allowlist aprendida; timeout de pergunta nega (fail-closed) |
| **Antigravity** | `Require Review` (só allowlist roda) ou `Always Proceed` (só denylist pergunta); precedência Deny > Ask > Allow. Usuários relatam allowlist que não persiste e "Always Proceed" ignorado | Precedência igual à nossa (ADR-023); a fricção vem de bugs de persistência, o que reforça ligar o ledger com testes |

**Conclusões para o ORION**
1. Classificar por **raio de destruição e reversibilidade**, não por tool. `rm` num repositório commitado é desfazível; `dd` num disco não é.
2. A melhor forma de evitar perguntas é **tornar reversível** o que hoje não é (snapshot antes de apagar). Pedir senha para o desfazível é ritual vazio.
3. Senha só para o irreversível que o ORION não consegue desfazer. Para `sudo` comum, quem verifica é o próprio `sudo` (askpass); lembrar a senha só no chaveiro do SO, com um helper fora do alcance do modelo.
4. Sem humano, escalar para a Inbox em vez de negar.

---

## 4. Senha do SO: opções técnicas avaliadas

| Opção | Verifica de verdade? | Atrito | Risco | Decisão |
|:--|:--|:--|:--|:--|
| Popup zenity/kdialog que só checa "não vazio" (atual) | Não | Médio | Falsa sensação de segurança | Remover |
| `SUDO_ASKPASS` + `sudo -A` | Sim (o próprio sudo, via PAM) | Baixo, com o cache de timestamp do sudo | Nenhum novo | Adotar |
| Senha no chaveiro do GNOME (Secret Service) lida por um helper fora do modelo | Sim (o sudo verifica) | Zero para `sudo` comum | Um processo do usuário com o chaveiro aberto pode ler a entrada; mitigado por: opt-in, preencher só o que o classificador marcou não destrutivo, nunca para Nuclear | Adotar como opt-in (`orion setup sudo`) |
| Drop-in `/etc/sudoers.d/orion` com NOPASSWD para comandos listados | Não se aplica (sem senha) | Zero | Lista mal feita vira escalada; mitigado por revisão do Senhor e `visudo -c` | Oferecer como alternativa mais forte |
| `pkexec` / polkit | Sim | Baixo (diálogo nativo do GNOME) | Nenhum novo | Adotar para Nuclear |
| PAM do próprio usuário (`python-pam` → `unix_chkpwd`, sem root) | Sim | Baixo (overlay mascarado na TUI) | A senha passa pelo processo do ORION; nunca é logada | Adotar para Nuclear na TUI e sem display |
| Senha guardada na memória do ORION / arquivo | — | Zero | Injeção de prompt ganharia root; viola ADR-042 | Rejeitado |
| fprintd (digital) | Sim | Mínimo | — | Usar quando houver leitor |

---

## 5. Fontes
- Anthropic, "Claude Code auto mode" (engenharia): https://anthropic.com/engineering/claude-code-auto-mode
- Hermes Agent, memória: https://hermes-agent.nousresearch.com/docs/user-guide/features/memory
- Hermes Agent, segurança: https://hermes-agent.nousresearch.com/docs/user-guide/security
- Mastra, Observational Memory: https://mastra.ai/research/observational-memory
- Letta, sleep-time agents: https://docs.letta.com/guides/agents/architectures/sleeptime/index.md
- Mem0, State of AI Agent Memory 2026: https://mem0.ai/blog/state-of-ai-agent-memory-2026
- "Does Memory Need Graphs?" (2026): https://arxiv.org/pdf/2601.01280
- "MemDelta: Controlled Baselines and Hidden Confounds in Agent Memory Evaluation": https://arxiv.org/pdf/2606.29914
- Antigravity, permissões: https://antigravity.google/docs/permissions
- python-pam: https://pypi.python.org/pypi/python-pam
