# Sprint — v0.5.2 Sprint 3: Movimento

> **Status:** ✅ Implementada em 16/11/2026 · **ADR:** 045 · **Achados:** N-06 a N-17, N-22 a N-24 · **CA:** CA-09

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

## Registro de implementação (16/11/2026)
- `stream_renderer.py` (vale para os dois modos): `Pensando · 3,2s · 412 tok · esforço baixo · <cancelar>`; linha viva com a última frase do raciocínio; `Escrevendo · Ns` durante o texto; cabeçalho `▸ Raciocínio · 4,1s · 1,2k tok`; raciocínio < 1 s e < 80 caracteres absorvido; respiro entre blocos da mesma fala; código com até 3 linhas sem moldura; erro de schema traduzido; `turn_summary` (chamado pela sessão com tempo, tokens e custo do turno).
- `status_bar.py`: `Pronto`, `Trabalhando`, `US$ 0,000`, `esforço médio`, `(rápido)`; modo e PEP presentes em qualquer largura (testado de 60 a 110 colunas).
- PEP: título `[PEP] Autorização requerida · ação de nível N` (o `PEP N` da status line é o modo da sessão); decisão sem recuo com `· ação de nível N`; na tela cheia, `● Aguardando autorização do Senhor` na linha de atividade.
- `tui/screen/terminal.py`: synchronized output no `flush` de cada quadro, título da aba, OSC 9;4, eventos de foco (spinner a 2 quadros/s sem foco; sino ao fim de turno > 10 s sem foco).
- Ctrl+O: transcrição com tudo aberto, `/` busca, `n`/`N`, `j`/`k`, `g`/`G`, `[` despeja a conversa em cores no scrollback normal e volta com Enter, `q`/Esc saem.
- Banner e `/help`: `Alt+T esforço` e atalhos da tela cheia.
- Validação no `tui-mcp`: linha viva do raciocínio, rodapé `✔ 32,2s · 1,8k tok · US$ 0,0086`, PEP com nível da ação, busca "tratamento formal" 9/9 na transcrição completa.
- Corrigido na validação: status line em negrito (`nobold`) e duas linhas em branco entre pedido e raciocínio.
- Testes: `test_stream_motion.py` (16) e testes antigos atualizados para os textos novos; lab completo verde.
- **Desvio:** o `v` (abrir no `$EDITOR`) do Claude Code não entrou; `[` cobre a busca nativa.
