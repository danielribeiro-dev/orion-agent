# Visão: 10 superpoderes (propostas de versão)

> **Status:** PROPOSTA, aguardando decisão do Senhor. Nada aqui é spec congelada, nenhum ADR foi criado e nada em `src/` muda por causa deste documento (Doc-First).
> **Data:** 17/11/2026. **Origem:** conversa de estratégia de lançamento; critério = "o que a comunidade abraça e o que serve no dia a dia".
> **Relação com o roadmap:** reaproveita versões já planejadas (v0.5.3, v0.6.0, v0.7.0, v1.5.0, v2.0.0, v3.0.0) e propõe encaixes novos. Complementa `living-memory-and-ambient-jarvis.md` e `ambient-panel-and-voice.md`.

## Regras que valem para todos os superpoderes

1. Toda ação mutante continua passando pelo PEP. Nenhum superpoder cria atalho de autorização.
2. Ação nuclear exige step-up do SO. Voz, GUI, agendamento e regras aprendidas nunca substituem isso.
3. Brain/Body: `orion.core` não faz I/O; cada poder entra como adaptador/porta.
4. Dados só em `~/.orion/`. Tudo que escuta, observa ou grava a máquina é opt-in e separado do autostart do daemon.
5. Custo: nenhum teste automático chama provedor pago (`ORION_LIVE=1` e `BudgetGuard`).
6. Idle continua em zero token (ADR-022).

## Visão geral

| # | Superpoder | Versão sugerida | Já existe | Esforço | Apelo à comunidade |
|---|---|---|---|---|---|
| 1 | Voz Jarvis local | v0.6.0 (planejada) | daemon, IPC, roteador de saída | Alto | Muito alto |
| 2 | Memória viva e máquina do tempo | v0.5.3 (base) + v0.8.0 (máquina do tempo) | timeline, FTS5, `/recall`, `/rewind` | Alto | Alto |
| 3 | Sentinela proativo | v0.6.x (observadores) e v1.5.0 (autocura) | scheduler, jobs, notificações | Médio | Muito alto |
| 4 | Autonomia graduada | v0.6.x | PEP, trust ledger | Médio | Alto (segurança) |
| 5 | Cockpit eDEX com agentes à vista | v0.7.0 (planejada) | eventos, tasks, `/agents` | Alto | Muito alto (visual) |
| 6 | ORION Imortal (offline de verdade) | v0.6.x (UX e demo) | failover Ollama < 2 s (v0.3.0) | Baixo | Muito alto |
| 7 | Mãos na GUI e no browser | v2.0.0 / v2.5.0 | PEP, MCP | Muito alto | Alto |
| 8 | Skills que se escrevem + hub | v0.8.0 | `SKILL.md`, skills, `/learn` (roadmap) | Médio | Muito alto (contribuição) |
| 9 | Transparência radical de custo | v0.5.3 / v0.6.0 | ledger, `BudgetGuard`, `/cost`, `bench_mcp_tokens.py` | Baixo | Alto |
| 10 | ORION em todos os dispositivos | v3.0.0 | Telegram, IPC do daemon | Muito alto | Médio-alto |

Ordem sugerida de decisão: 6 e 9 (baratos e já têm base), depois 1, 3 e 4 (v0.6.0 vira "ORION presente"), depois 5 (v0.7.0), 8 e 2, e por fim 7 e 10.

---

## 1. Voz Jarvis local

- **Ideia:** wake word, fala para texto e texto para fala 100% locais; o ORION fala e pede aprovação ("Senhor, posso executar…?").
- **Base:** `docs/architecture/AMBIENT_VOICE.md`, ADR-032/034, roteador de saída (cliente anexado, notificação, Telegram, voz).
- **MVP:** push-to-talk e TTS primeiro; wake word depois. Voz é só mais um cliente do IPC do daemon.
- **Limites:** aprovação por voz vale até o nível definido no PEP; ações nucleares exigem step-up do SO. Escuta contínua é opt-in separada. Respeita modo silencioso, bateria e orçamento.
- **Critério de aceite narrativo:** "Com o daemon ligado, digo o nome dele, peço para rodar os testes; ele responde por voz, pede aprovação, executa e me conta o resultado, sem tocar no teclado."
- **Riscos:** latência, falso positivo do wake word, ruído ambiente, privacidade (nada de áudio sai da máquina).

## 2. Memória viva e máquina do tempo

- **Ideia:** "o que eu estava fazendo na terça?", "por que escolhi essa lib?". Depois, voltar a um estado anterior de arquivos e decisões.
- **Base:** ADR-027, v0.5.3 (R-06, R-16, R-17), timeline com branches, `/rewind`, `/diff`, `/undo`.
- **MVP (v0.5.3):** memorização confiável (resolver R-06) e prompt base menor (R-16).
- **Extensão (v0.8.0):** linha do tempo ligada a snapshots (git ou equivalente) por projeto; "restaurar como estava em D".
- **Limites:** restauração é ação mutante (PEP). Esquecimento e exportação sob controle do Senhor.
- **Critério:** "Pergunto o que decidi sobre autenticação há um mês e ele responde com data, contexto e a decisão `CONFIRMED`."
- **Riscos:** crescimento do banco, memória errada virando verdade (manter `INFERRED` separado de `CONFIRMED`).

## 3. Sentinela proativo

- **Ideia:** observadores no daemon (CI falhou, disco enchendo, PR comentado, serviço caído, build quebrado) que só acordam o modelo quando há algo a decidir; briefing matinal; "acordei com o PR pronto".
- **Base:** scheduler durável, jobs, notificações (desktop, Telegram, Inbox), `daemon.pressure`.
- **MVP:** observadores como plugins simples (regra determinística, sem modelo) + triagem barata para decidir se vale acordar.
- **Evolução (v1.5.0):** autocura sob PEP: o ORION propõe a correção e aplica só com aprovação (ou regra aprendida, ver item 4).
- **Critério:** "Deixo o ORION a noite toda; de manhã há um resumo na Inbox, com a única falha de CI já diagnosticada e o patch proposto."
- **Riscos:** spam de notificação, custo oculto (medir tokens por observador), ações automáticas indevidas.

## 4. Autonomia graduada

- **Ideia:** o Senhor escolhe quanto confia, de "pergunta tudo" a "pergunta só o perigoso". O PEP percebe padrões ("aprovou 20 vezes `pytest`") e propõe transformar em regra.
- **Base:** PEP (níveis 0 a 3), trust ledger, regras e hooks.
- **MVP:** sugestão de regra a partir do histórico de aprovações, sempre confirmada pelo Senhor; regra visível, editável e revogável.
- **Limites:** regras nunca cobrem ação nuclear nem sobem acima do teto do subagente; aprendizado nunca silencioso.
- **Critério:** "Depois de uma semana, o ORION sugere liberar `pytest` neste projeto; aceito em um clique e as aprovações repetidas somem."
- **Riscos:** regra ampla demais (casar por padrão estreito), envenenamento de histórico, deriva de confiança.

## 5. Cockpit eDEX com agentes à vista

- **Ideia:** app desktop (Tauri v2 + WebGL) com telemetria real, árvore de arquivos tátil e cada subagente como processo vivo (custo, tempo, estado). Sequência de boot cinematográfica.
- **Base:** v0.7.0 planejada, `TUI_DESIGN_SYSTEM.md`, stream de eventos, tasks e subagents, aba ambiente.
- **MVP:** painel somente leitura sobre o IPC do daemon (telemetria + agentes); depois interação (aprovar, interromper).
- **Limites:** é só cliente do daemon, sem lógica de agente. GNOME/Wayland sem layer-shell: fallback para bandeja (ver `ambient-panel-and-voice.md`).
- **Critério:** "Abro o cockpit e vejo três subagentes trabalhando, o custo subindo em tempo real e um modal de aprovação pronto para tocar."
- **Riscos:** custo de design/engenharia; é a versão que mais compete com tempo do núcleo. Manter o terminal como cidadão de primeira classe.

## 6. ORION Imortal (offline de verdade)

- **Ideia:** a máquina perde a rede e o ORION continua, com modelo local e memória intacta; ao voltar, reconcilia sem conflito.
- **Base:** v0.3.0 (failover para modelo local em menos de 2 s, Ollama).
- **MVP:** modo offline explícito no rodapé, aviso claro de capacidade reduzida, `/doctor` checando o modelo local, script de demo.
- **Critério:** "Desligo o wifi no meio de uma tarefa; o rodapé muda para offline, o ORION termina com o modelo local e, ao voltar a rede, reconcilia."
- **Riscos:** qualidade do modelo local; prometer só o que ele cumpre (tarefas simples), sem exagero de marketing.

## 7. Mãos na GUI e no browser

- **Ideia:** controlar apps gráficos (AT-SPI2, entrada sintética) e o Chrome (CDP) para "abre, preenche, testa".
- **Base:** roadmap v2.0.0 (Ghost Input, CDP, cofre Zero-Knowledge) e v2.5.0 (interação espacial).
- **MVP:** só CDP (browser) em modo leitura e depois ação, cada clique/ digitação passando pelo PEP.
- **Limites:** níveis altos de PEP; credenciais só via cofre; nunca em páginas de pagamento/ banco sem step-up.
- **Critério:** "Peço para reproduzir um bug numa página; o ORION abre, navega, captura o erro e anexa a evidência, pedindo aprovação em cada ação mutante."
- **Riscos:** o maior risco de segurança do projeto (injeção de prompt via página). Só entra depois de o PEP estar provado em campo.

## 8. Skills que se escrevem e hub comunitário

- **Ideia:** o ORION percebe o que o Senhor repete e propõe uma skill; um catálogo aberto de `SKILL.md` deixa a comunidade contribuir.
- **Base:** skills (`SKILL.md`), roadmap com auto-destilação (`/learn`), MCP.
- **MVP:** `/learn` gera rascunho de skill revisável; repositório de skills da comunidade com validação (lint do formato e do nível PEP).
- **Limites:** skill de terceiros nunca eleva privilégio; mostrar quais tools e níveis PEP ela pede antes de instalar; assinatura/hash para versões.
- **Critério:** "Instalo uma skill da comunidade e vejo, antes de ativar, exatamente o que ela pode tocar."
- **Riscos:** supply chain (skills maliciosas). Exigir revisão e sandbox desde o dia um.

## 9. Transparência radical de custo

- **Ideia:** painel de gasto por dia, projeto e tarefa; roteamento para o modelo mais barato que resolve; benchmarks públicos de tokens.
- **Base:** cost ledger, `BudgetGuard`, roteamento por complexidade, `scripts/bench_mcp_tokens.py`.
- **MVP:** `/cost` com histórico e visão semanal; publicar um benchmark reprodutível (tokens por tarefa-padrão) no repositório.
- **Critério:** "Vejo quanto gastei na semana, em USD e BRL, por projeto, e o que o roteador economizou."
- **Riscos:** comparar com concorrentes sem metodologia justa; publicar só o que é reprodutível.

## 10. ORION em todos os dispositivos

- **Ideia:** notebook, servidor e celular compartilhando memória e fila; "continua no celular de onde parei".
- **Base:** roadmap v3.0.0, Telegram como primeiro canal, IPC do daemon.
- **MVP:** cliente móvel leve (inbox, aprovar/negar) falando com o daemon por canal autenticado.
- **Limites:** criptografia ponta a ponta, sem nuvem própria; aprovação remota nunca cobre ação nuclear.
- **Critério:** "Aprovo no celular um deploy pedido pelo ORION no servidor, e a decisão fica na linha do tempo."
- **Riscos:** superfície de ataque nova; fica por último de propósito.

---

## Próximos passos (se o Senhor aprovar)

1. Escolher quais entram em qual versão e registrar a decisão em `.claudex/decisions.md` (novos ADRs).
2. Atualizar `docs/planning/ROADMAP.md` com a ordem escolhida.
3. Só então escrever `VERSION.md` e `sprints/sprint-N.md` de cada versão (um superpoder por sprint, no máximo).
4. Para cada superpoder, definir o nível PEP das tools novas antes de qualquer código.
