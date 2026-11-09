# Visão: Memória Viva e Jarvis Ambiente (proposta)

> Status: PROPOSTA (08/11/2026). Nada aqui autoriza código em `src/`: cada item precisa de spec de versão/sprint congelada (Doc-First). Base: ADR-027.

## Frase fundacional
O ORION é a segunda metade do Senhor, vive no computador e não em um projeto. Memória e aprendizado são sua maior virtude. Nada se perde, tudo se transforma.

## Cenários-alvo (critérios de aceite narrativos)
1. **Diretiva:** "Quando eu chamar Jarvis/Orion, responda 'Sim, senhor'" e "quando eu disser 'Jarvis tá aí', responda 'Para o senhor, sempre'". Persiste entre sessões e projetos, sem chamar LLM quando o gatilho é exato.
2. **Memória de decisão e infra:** "usamos Postgres 15 no servidor X, deploy via Y" lembrado em qualquer projeto relacionado, com origem e data.
3. **Nível de habilidade:** o perfil de maestria por domínio evolui por observação (ex.: o Senhor domina Python, está aprendendo Rust) e ajusta a profundidade das explicações.
4. **Skill por intenção:** "Jarvis, ative o protocolo babá" ativa a skill sem `/`. Protocolo e skill são a mesma coisa; o protocolo é só a skill usada de forma dinâmica (por voz/intenção, com watchers).
5. **Higiene:** depois de semanas, a memória não tem duplicatas nem contradições vivas; fatos superados apontam para o sucessor.

## Estado atual (verificado no código)
- Existem: `FactsStore` (fatos CONFIRMED/DEPRECATED com anti-envenenamento), `HybridRetriever` (BM25 + vetores), `TimelineManager`, `AutoRecall` (injeção por turno, 1.500 tokens), tools `memorize`/`recall`/`deprecate_fact`, manifesto cognitivo, perfil com matriz de maestria (v0.2.0).
- Lacunas: sem escopo global/projeto/organização explícito; sem aprendizado por observação ativa nem inferência provisória; sem consolidação/fusão/linhagem; sem diretivas permanentes; sem roteamento de skill por intenção; sem export/import de memória. Nenhum turno com provedor real foi validado ainda.

## Versões e sprints propostas (a decidir pelo Senhor)
| Proposta | Foco | Itens |
| :--- | :--- | :--- |
| **Memória Viva** (depois do gate de dogfooding; sugestão: nova versão entre v0.5.0 e a voz) | Aprender e higienizar | Escopos de memória (global/org/projeto/dispositivo); captura por observação com proveniência e confiança; fatos PROVISÓRIOS vs CONFIRMADOS; consolidador (fusão, `supersedes`, resumo de episódios); perfil de habilidade por domínio; revisão periódica no daemon (zero token em idle, ADR-022); identidade carrega o ADR-027 |
| **Diretivas e Skills por Intenção** | Comportamento ensinável | Diretivas permanentes em linguagem natural (gatilho exato determinístico + gatilho semântico com triagem barata); ativação de skill por intenção via manifesto; skills do usuário criadas por conversa (`/learn`) |
| **Interface** (já pendente: F-09) | TUI | Agrupar o F-09 e as mudanças de interface que o Senhor trouxer; decidir se entra antes da voz |
| **v0.6.0 Ambient/Voz** (já no ROADMAP) | Falar com ele | Wake word, STT, TTS sobre o daemon; as diretivas e o roteamento por intenção são pré-requisito para "Jarvis, ative o protocolo babá" por voz |
| **Protocolos = Skills dinâmicas** (após daemon e voz) | Monitorar e agir | "Protocolo" não é um conceito novo: é uma skill (`SKILL.md`) ativada por intenção e que pode instalar watchers no daemon. Sem tipo novo de artefato: reaproveita skills, PEP e daemon. Watchers de processo/jogo/janela; ações via PEP; consentimento explícito e auditoria; apenas contas/dispositivos do Senhor |
| **v3.0.0 Simbiose** (já no ROADMAP) | Multi-dispositivo | Memória portável cifrada, sincronização, celular/pendrive; formato definido já na Memória Viva para não retrabalhar |

## Riscos e limites
- **Autoaprendizado envenenável:** inferência nunca vira CONFIRMED sozinha; conteúdo de web/MCP/terceiros é dado, nunca instrução.
- **Privacidade:** observar o que o Senhor faz exige lista do que é observado, `/memory` para inspecionar, editar e esquecer, e opt-in por fonte.
- **Protocolo babá:** monitorar terceiros (o irmão) é sensível; escopo limitado ao dispositivo do Senhor, transparente para quem usa, e nunca ação nuclear sem step-up.
- **Custo:** observar e consolidar não pode chamar LLM em idle; usar regras determinísticas, e modelo barato só em lote com teto no `BudgetGuard`.
