# Visão: superpoderes 11 a 25 (propostas) e ideias 26 a 35

> **Status:** PROPOSTA, aguardando decisão do Senhor. Sem ADR, sem spec congelada, nada em `src/` muda (Doc-First).
> **Data:** 17/11/2026. Continuação de [`superpoderes-propostas.md`](superpoderes-propostas.md) (itens 1 a 10); as mesmas regras gerais valem aqui (PEP em toda ação mutante, step-up nuclear, Brain/Body, dados só em `~/.orion/`, idle = 0 token, nada pago em teste).
> **Specs existentes a reconciliar:** `docs/specs/superpowers/01` a `06` (ver tabela no primeiro documento).

## Visão geral (itens 11 a 25)

| # | Superpoder | Versão sugerida | Esforço | Relação com spec existente |
|---|---|---|---|---|
| 11 | Replay de sessão | v0.6.x | Baixo | nenhuma |
| 12 | Standup e devlog automáticos | v0.6.x | Baixo | parcial: 06 §2.4 (Morning Summary) |
| 13 | Preview de impacto | v1.5.0 | Médio | usa o sandbox da 04 |
| 14 | Perfis de projeto portáteis | v0.6.x | Baixo | nenhuma |
| 15 | Issue para PR em worktree isolado | v0.8.0 | Médio | nenhuma |
| 16 | Cofre com redação automática | v0.8.0 | Médio | complementa 03 (keyring e voz) |
| 17 | Modo Unix e socorro no terminal | v0.6.x | Baixo | nenhuma |
| 18 | Modo Mentor | v0.8.0 | Médio | nenhuma |
| 19 | Atlas do código | v0.8.0 | Alto | usa Tree-sitter da 04 |
| 20 | Conselho | v0.8.0 | Médio | nenhuma |
| 21 | Modo Sombra | v1.5.0 | Médio | parcial: 06 e 02 |
| 22 | Importador universal | v0.6.x | Baixo | nenhuma |
| 23 | Temas e personas | v0.7.0 | Baixo | depende do cockpit |
| 24 | Faxineiro | v0.8.0 | Baixo | nenhuma |
| 25 | Desafio "Quebre o PEP" | pós v1.0 | Médio | nenhuma |

Ordem sugerida: 22, 17, 14, 11 e 12 primeiro (baratos, derrubam atrito e geram conteúdo); 24, 18, 20 e 15 depois; 19, 21 e 16 com os specs 04/06/03 reconciliados; 13 com o sandbox; 25 só depois da v1.0.

---

## 11. Replay de sessão
- **Ideia:** reproduz uma sessão como filme (pensamento, tools, aprovações, custo) e exporta HTML autocontido ou `.cast`.
- **Base:** log de auditoria event-sourced, `/rewind`, sessões.
- **MVP:** `orion replay <sessão>` na TUI com velocidade ajustável; exportação com segredos e caminhos pessoais redigidos por padrão.
- **Critério:** "Exporto uma sessão em um arquivo que qualquer pessoa abre no navegador e vê o que o ORION fez, incluindo cada aprovação do PEP."
- **Riscos:** vazar dados na exportação (redação obrigatória e revisão antes de salvar).

## 12. Standup e devlog automáticos
- **Ideia:** `/standup` resume o dia; `/devlog` gera changelog e rascunho de post de build in public a partir da timeline.
- **Base:** timeline, `/recall`, sessões, perfil do usuário.
- **MVP:** resumo diário em texto, com opção de tom (técnico, LinkedIn, curto). Nunca publica nada sozinho.
- **Critério:** "Ao fim do dia recebo um resumo fiel do que decidi e entreguei, pronto para colar num post."
- **Riscos:** alucinar feitos que não ocorreram (citar a linha da timeline de cada afirmação).

## 13. Preview de impacto
- **Ideia:** antes de aprovar uma ação do PEP, ver o que mudaria: arquivos tocados, processos, rede, espaço.
- **Base:** PEP, spec 04 (Bubblewrap `bwrap`).
- **MVP:** dry-run em sandbox para comandos de shell; lista de caminhos afetados no modal.
- **Critério:** "O modal de aprovação mostra os arquivos que o comando alteraria, calculados antes de rodar."
- **Riscos:** o preview divergir da execução real; marcar claramente quando é estimativa.

## 14. Perfis de projeto portáteis
- **Ideia:** `.orion/project.toml` versionado com regras, skills, MCPs, teto de orçamento e nível de PEP do projeto.
- **Base:** rules, hooks, skills, `BudgetGuard`, confiança de projeto.
- **MVP:** leitura do perfil com confirmação de confiança na primeira abertura; perfil nunca eleva privilégio acima do teto do usuário.
- **Critério:** "Clono um repositório com perfil, o ORION mostra o que ele pede e, após eu confiar, todo mundo da equipe usa as mesmas regras."
- **Riscos:** repositório hostil tentando configurar o agente (confiança explícita e deny by default).

## 15. Issue para PR em worktree isolado
- **Ideia:** marcar uma issue, o ORION trabalha numa worktree, roda testes e entrega branch, relatório e custo, sem tocar na `main`.
- **Base:** subagentes, worktrees (falha fechada), tasks, daemon.
- **MVP:** comando manual `orion issue <n>` antes da automação por rótulo.
- **Critério:** "De manhã encontro uma branch com testes verdes e um relatório de custo; merge e push seguem sendo meus."
- **Riscos:** custo descontrolado (teto por tarefa), escopo vazando, prompt injection vindo do texto da issue.

## 16. Cofre com redação automática
- **Ideia:** o agente usa segredos pelo nome; o valor é injetado no processo filho e removido de logs, transcrição e memória.
- **Base:** ADR-042 (`~/.orion/.env` que o agente não lê), spec 03 (Secure Vault, keyring).
- **MVP:** filtro de redação sobre saída de tools e transcrição para valores registrados no cofre.
- **Critério:** "Rodo um script que usa uma chave; ela não aparece em log, transcrição, memória nem auditoria."
- **Riscos:** redação por correspondência perde segredos transformados (base64); documentar o limite.

## 17. Modo Unix e socorro no terminal
- **Ideia:** `git diff | orion "explique"`, `orion -p` para scripts, widget de shell (bash, zsh, fish) e `orion fix` para o último comando que falhou.
- **Base:** CLI, sessões, PEP.
- **MVP:** modo não interativo com PEP em modo "negar mutações" por padrão; `fix` só propõe, não executa.
- **Critério:** "Um comando falha, digito `orion fix` e recebo o diagnóstico e o comando corrigido para aprovar."
- **Riscos:** entrada de pipe como vetor de prompt injection; tratar stdin como dado.

## 18. Modo Mentor
- **Ideia:** explica cada passo, faz quiz do que acabou de acontecer e transforma a timeline em notas de estudo.
- **Base:** memória, perfil do usuário (matriz de maestria), `/memory`.
- **MVP:** flag de sessão `mentor` que acrescenta explicação curta e pergunta de verificação ao fim de cada tarefa.
- **Critério:** "Depois de uma tarefa, o ORION me pergunta duas coisas sobre o que fez e registra o que errei na matriz de maestria."
- **Riscos:** virar ruído para quem não quer (opt-in, desligável por turno).

## 19. Atlas do código
- **Ideia:** mapa vivo do repositório com grafo de dependências e diagramas Mermaid; responde "onde isso é usado?".
- **Base:** spec 04 (Tree-sitter), embeddings locais, `/context`.
- **MVP:** índice local por projeto e comando `/atlas` que gera diagrama de um módulo.
- **Critério:** "Peço o mapa do módulo X e recebo um diagrama correto das dependências, sem mandar código para fora."
- **Riscos:** índice defasado (invalidação por git), custo de indexação em repositório grande.

## 20. Conselho
- **Ideia:** pergunta crítica passa por subagentes com papéis (arquiteto, advogado do diabo, segurança) e o ORION sintetiza.
- **Base:** subagentes com teto de privilégio, roteador, ADRs.
- **MVP:** `/council <pergunta>` com 3 papéis fixos, teto de custo e saída em formato de ADR proposto.
- **Critério:** "Recebo a síntese com os argumentos de cada lado e o custo total antes de confirmar a execução."
- **Riscos:** custo multiplicado (confirmação de custo obrigatória), concordância falsa entre papéis.

## 21. Modo Sombra
- **Ideia:** com opt-in, acompanha o `git diff` e prepara testes e revisão antes de o Senhor pedir; entrega na Inbox.
- **Base:** daemon, Inbox, `/review`, specs 06 e 02.
- **MVP:** observação só do repositório ativo, sem tela nem teclado.
- **Critério:** "Ao terminar uma alteração encontro na Inbox testes sugeridos e uma revisão curta, sem ter pedido."
- **Riscos:** custo contínuo (acordar o modelo só após pausa longa e diff relevante) e sensação de vigilância.

## 22. Importador universal
- **Ideia:** `orion import` lê `CLAUDE.md`, `AGENTS.md`, `.cursorrules`, configs de MCP e skills de outras ferramentas.
- **Base:** skills `SKILL.md`, MCP, rules.
- **MVP:** importar apenas o que é texto/declarativo, com revisão item a item e PEP dos MCPs preservado.
- **Critério:** "Em um minuto o ORION usa as regras e os MCPs que eu já tinha em outra ferramenta, depois de eu aprovar cada um."
- **Riscos:** importar instruções maliciosas (tratar tudo importado como não confiável até aprovação).

## 23. Temas e personas compartilháveis
- **Ideia:** skins do cockpit e da TUI, sons e vozes, em arquivos que se trocam.
- **Base:** design tokens, persona modular, `TUI_DESIGN_SYSTEM.md`.
- **MVP:** temas só de cor/tokens na TUI antes do cockpit. Respeita a regra de glifos permitidos.
- **Critério:** "Instalo um tema da comunidade em um comando e posso voltar ao padrão."
- **Riscos:** tema degradar legibilidade (contraste mínimo validado).

## 24. Faxineiro
- **Ideia:** acha caches, imagens Docker, venvs órfãos e `node_modules` antigos; mostra o espaço que liberaria e limpa com aprovação.
- **Base:** PEP, daemon, `daemon.pressure`.
- **MVP:** relatório somente leitura primeiro; limpeza por categoria com PEP nível adequado.
- **Critério:** "Vejo a lista com tamanho de cada item e aprovo apenas o que quero apagar."
- **Riscos:** apagar o que não devia (nunca fora de listas conhecidas; nada sem aprovação; lixeira quando possível).

## 25. Desafio "Quebre o PEP"
- **Ideia:** desafio público de segurança com ranking e correções divulgadas.
- **Base:** `tests/e2e/test_security_audit.py`.
- **MVP:** ambiente descartável, regras claras, política de divulgação responsável (`SECURITY.md`).
- **Critério:** "Qualquer pessoa reproduz o ambiente do desafio e envia um relato de bypass; cada achado vira teste de regressão."
- **Riscos:** só lançar com o PEP bem coberto; ter resposta pública pronta para o primeiro bypass.

---

## Ideias de patamar seguinte (26 a 35, ainda sem proposta)

Conferido por busca em `src/`, `docs/` e `.claudex/` em 17/11/2026: não há plano nem código para nenhuma delas (a busca é textual e pode ter perdido algo).

| # | Ideia | O que muda |
|---|---|---|
| 26 | **Livro de saída de dados e zonas só-locais** | Registro inspecionável de tudo que saiu da máquina para cada provedor, redação de segredos e dados pessoais antes de sair, e pastas marcadas como "só local" que forçam modelo local. |
| 27 | **Recibos assinados e cadeia de auditoria à prova de adulteração** | Auditoria encadeada por hash com assinatura; qualquer pessoa verifica que o registro não foi alterado. Base para uso em empresa. |
| 28 | **Arena pessoal e roteador que aprende** | Reexecuta tarefas reais suas (via replay) em vários modelos, pontua por testes e custo, e o roteador passa a escolher com base nos seus resultados. |
| 29 | **Cristalizador** | O que o modelo resolveu três vezes vira script determinístico com testes; da quarta vez roda sem token. Parente do autoclicker cognitivo da spec 02, mas no nível de tarefas de código e comandos. |
| 30 | **Laboratório de autoaperfeiçoamento supervisionado** | O ORION lê as próprias falhas (achados de dogfooding, `tests/lab`) e propõe correções de código, prompts e skills em branch, usando a suíte como função de aptidão. Nunca faz merge nem se atualiza sozinho. |
| 31 | **Verificador formal da política** | Política do PEP como código, com invariantes verificadas ("nenhum caminho apaga `~/.ssh` sem step-up") por teste de propriedade ou verificação de modelo. |
| 32 | **Federação de ORIONs** | Instâncias de pessoas diferentes trocam pedidos com escopo e consentimento (a letra N do nome), sem expor memória. |
| 33 | **Memória de equipe com promoção revisada** | Fatos pessoais sobem para o conhecimento da equipe por revisão (como um PR), com redação e procedência. |
| 34 | **Bancada de hardware e ações físicas** | Serial/USB, microcontroladores, impressora 3D e automação residencial via MCP, com uma nova classe de PEP para ações que movem o mundo físico. |
| 35 | **Teletransporte de ambiente** | Em máquina nova (Linux, Mac ou Windows) o ORION recria seu ambiente (pacotes, dotfiles, repositórios, preferências) a partir da memória e do cofre, com aprovação por etapa. |

Ficaram de fora por ora: currículo vivo com evidências do trabalho real, estúdio de vídeo narrado a partir do replay e política de interrupção (decidir quando vale incomodar o Senhor).
