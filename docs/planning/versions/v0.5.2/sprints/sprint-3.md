# Sprint — v0.5.2 Sprint 3: Movimento

> **Status:** ⏳ · **ADR:** 045 · **Achados:** N-06 a N-17, N-22 a N-24 · **CA:** CA-09

## Escopo
1. Pensamento: linha viva com tempo, tokens estimados e última frase; bloco `▸`/`▾`; raciocínio curto absorvido.
2. Atividade durante o texto (`Escrevendo · Ns`).
3. Erros de schema traduzidos (`parâmetros inválidos do modelo`), detalhe preservado na saída expansível.
4. Decisão PEP alinhada e com o nível da ação; status line explica `PEP` da sessão.
5. Rodapé de turno com tempo, ferramentas, tokens e custo do turno.
6. Markdown: respiro antes de títulos, código curto sem moldura, sem linhas em branco duplicadas.
7. Status line em PT-BR (`Pronto`, `Trabalhando`), `US$` com vírgula, modo e PEP preservados em qualquer largura.
8. Terminal: synchronized output, título da aba, OSC 9;4, sino ao terminar turno longo sem foco, spinner lento sem foco, Ctrl+L.
9. Banner: `Alt+T esforço`.
10. Transcrição (Ctrl+O): visão completa com busca e despejo no scrollback.

## Testes
`tests/unit/test_stream_motion.py`, `test_status_bar` atualizado, sequências de terminal verificadas no lab.
