# Achados de TUI — Catálogo N-01 a N-24 e auditoria A-01 a A-09 (v0.5.2)

> **Origem:** rodada de 15/11/2026 no ORION v0.5.0-alpha (commit `4dadba7`), `tui-mcp` com o provider roteirizado do lab (`tests/lab/launcher.py`), HOME isolado, custo zero. Roteiro: turno com raciocínio, `read_file`, `edit_file`, `run_command` com PEP e resposta em markdown; stream longo com pausa de 6 s e digitação durante o turno; `/memory`, `/timeline`, `/recall`, Alt+R; redimensionamento de 110x36 para 80x30. Auditoria: os 29 comandos rodados em lote no `LabTerminal`.
> **Confiança:** **C** = visto na captura · **H** = causa lida no código, confirmar com teste vermelho.

## Estrutura da tela

| ID | Conf. | Achado | Causa | Sprint |
|:---|:---:|:---|:---|:---:|
| N-01 | C | Depois do turno a tela "pula": o prompt vai ao topo e sobra área vazia abaixo | Live transiente some; o `PromptSession` redesenha a partir do cursor | 2 |
| N-02 | C | O input não existe durante o turno; o type-ahead ecoa uma linha `❯ texto` solta, sem moldura nem fila visível | `cli.py` alterna `prompt()` e `asyncio.run(run_turn)` | 2 |
| N-03 | C | Alt+R reimprime o raciocínio no fim do histórico, sem dizer de qual turno; o `│` só na primeira linha | `expand_reasoning` faz append; o modo inline não edita o passado | 2 |
| N-04 | C | Ao redimensionar, o histórico não refaz a quebra, surge régua duplicada e a status line perde modo e PEP | Scrollback é texto impresso; `status_segments` corta o PEP abaixo de 110 colunas | 2, 3 |
| N-05 | C | A mensagem do usuário fica no histórico entre duas réguas, idêntica a um input ativo | O bloco do prompt é congelado como foi digitado | 2 |

## Pensamento e ferramentas

| ID | Conf. | Achado | Sprint |
|:---|:---:|:---|:---:|
| N-06 | C | Ao pensar só aparece `Pensando [high effort]… (4,4s)`: nada do raciocínio, sem tokens, inglês entre colchetes | 3 |
| N-07 | C | Quando o texto começa, o spinner some: sem sinal de atividade nem tempo durante a escrita | 3 |
| N-08 | C | O bloco recolhido usa `▼` (que significa aberto), fora da tabela de glifos; sem respiro antes do texto | 3 |
| N-09 | C | O banner chama Alt+T de "raciocínio" (é o esforço) e o bloco diz `Alt+R expande` | 3 |
| N-10 | C | Raciocínio de 0,2 s entre ferramentas vira um bloco inteiro | 3 |
| N-11 | C | Erro de schema da tool aparece cru, em inglês (`Invalid parameters for 'edit_file'...`) | 3 |
| N-12 | C | O modal diz `PEP 3`, a status line `PEP 2`, sem explicar (nível da ação contra modo da sessão) | 3 |
| N-13 | C | `✔ aprovado` recuado, fora da coluna das ferramentas | 3 |
| N-14 | C | O turno não tem fim visível (tempo total, ferramentas, tokens, custo) | 3 |

## Ritmo e consistência

| ID | Conf. | Achado | Sprint |
|:---|:---:|:---|:---:|
| N-15 | C | Markdown sem ritmo: título colado ao parágrafo, duas linhas vazias depois do código | 3 |
| N-16 | C | Bloco de código de 2 linhas com moldura de largura total | 3 |
| N-17 | C | `$0.010` com ponto ao lado de `5,2s` com vírgula; `Ready`/`Working` em inglês | 3 |

## Memória e comandos

| ID | Conf. | Achado | Sprint |
|:---|:---:|:---|:---:|
| N-18 | C | `/timeline` e `/recall` despejam markdown achatado, sem truncar, papéis `user`/`assistant`, sem agrupar por dia | 4 |
| N-19 | H | `_print_record` pede `no_wrap` + reticências e a linha quebra mesmo assim | 4 |
| N-20 | C | `/memory` mostra o usuário do SO (`danieldev`) e nomes técnicos das esferas | 4 |
| N-21 | C | Listas sem padrão comum entre comandos | 4 |

## Pontos cegos

| ID | Achado | Sprint |
|:---|:---|:---:|
| N-22 | Sem synchronized output (DEC 2026): quadros pela metade em terminais lentos | 3 |
| N-23 | Sem título da aba com o estado, sem progresso nativo (OSC 9;4), sem aviso de fim com a janela sem foco | 3 |
| N-24 | Spinner anima sem foco; sem Ctrl+L de redesenho; nada fica no scrollback dizendo como retomar | 2, 3 |

## Auditoria dos comandos (29 rodados, 15/11/2026)

| ID | Comando | Achado | Correção | Sprint |
|:---|:---|:---|:---|:---:|
| A-01 | `/learn`, `/grill-me` | Sem argumento enviam um turno ao modelo (gasto sem pedido) | Recusar quando não há conversa a usar | 4 |
| A-02 | `/voice` | "O daemon de voz chega na v0.5.0." (versão errada) | "chega na v0.6.0" | 4 |
| A-03 | `/merge` | "Cannot merge 'main' into itself." em inglês | Mensagem em PT-BR | 4 |
| A-04 | `/context` | `0.0%` com ponto; janela `1000k` | Vírgula decimal; `1M` | 4 |
| A-05 | `/cost` | `$0.0000` com ponto ao lado de `R$ 0,000` | `US$ 0,0000` | 4 |
| A-06 | `/help` | Categorias em inglês (`memory`, `cognitive`); "memória tríplice" (são 5 esferas); jargão "RRF" | Categorias e descrições em PT-BR | 4 |
| A-07 | `/daemon` | Começa com `·` solto; "linger pelo ORION não" | Frase legível | 4 |
| A-08 | `/memory` | Ver N-20 | — | 4 |
| A-09 | `/timeline`, `/recall` | Ver N-18 | — | 4 |

Comandos sem achado: `/agents`, `/branch`, `/clear`, `/compact`, `/config`, `/diff`, `/doctor`, `/goal`, `/loop`, `/mcp`, `/model`, `/plan`, `/resume`, `/review`, `/rewind`, `/run`, `/skills`, `/tasks`, `/undo` (listas com moldura ficam como estão; o padrão `ListView` é aplicado só onde o texto era cru).

## Referências de mercado

- Claude Code — [Fullscreen rendering](https://code.claude.com/docs/en/fullscreen) e [Interactive mode](https://code.claude.com/docs/en/interactive-mode): tela alternativa, input fixo, fila, Ctrl+O, `[` para o scrollback, reserva após partida falha.
- Hermes — [CLI (espelho)](https://huggingface.co/spaces/lenson78/hermes/blob/main/website/docs/user-guide/cli.md): `/reasoning show|hide`, linhas apagadas durante ferramentas, `/verbose`.
- Codex — [chatwidget (espelho)](https://forge.lthn.ai/core/core-agent-ide/src/commit/641d5268fa581bbdff401e5e8e8cc346976b92fd/codex-rs/tui/src/chatwidget.rs): transcrição com Ctrl+T, título da seção de raciocínio.
- Toad — [Simon Willison](https://simonwillison.net/b/8855): re-render só do último bloco de markdown.
- Instalação nesta máquina: Hermes (`~/.local/bin/hermes` → venv privado em `~/.hermes`) e Claude Code (`~/.local/bin/claude` → `~/.local/share/claude/versions/<v>`).
