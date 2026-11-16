# Sprint — v0.5.2 Sprint 2: Casco em tela cheia

> **Status:** ⏳ · **ADR:** 043 · **Achados:** N-01 a N-05, N-24 · **CA:** CA-03 a CA-08, CA-11

## Objetivo
Uma `Application` em tela cheia com input sempre vivo, transcrição em células, rolagem e reflow, sem mudar o contrato `SessionSink`.

## Escopo
1. `tui/screen/transcript.py`: células (`renderables`, `kind`, `collapsed`, `toggle`), cache de linhas por largura, conversão Rich → fragmentos do prompt_toolkit, janela visível de baixo para cima.
2. `tui/screen/console.py`: `TranscriptConsole` (subclasse de `rich.Console`) cujo `print` grava células, `clear` limpa a transcrição e `status` vira linha de atividade.
3. `tui/screen/renderer.py`: `ScreenRenderer(StreamRenderer)` sem `Rich.Live`; a parte viva é desenhada pela app; `expand_reasoning`/`expand_output` alternam a célula no lugar.
4. `tui/screen/app.py`: layout (transcrição, fila, atividade, réguas, input, status), turnos como task, fila (Enter enfileira; Esc/Ctrl+C interrompem; ↑ retoma), rolagem (PgUp/PgDn, Ctrl+Home/End, roda do mouse), overlays para `run_modal` e perguntas de texto, resumo ao sair.
5. `modal.py`: `run_modal` e as perguntas de texto delegam ao host ativo.
6. `cli.py`: escolha do renderizador (`ORION_TUI`, `ui.tui`, TTY, `TERM`, contador de partidas falhas) e comando `/tui`.

## Testes
Unitários da transcrição, do console, do renderer e da escolha do modo; cenário de lab `test_fullscreen.py` (input vivo, fila, reflow, saída, ocioso). O lab da v0.5.1 continua no modo clássico (`ORION_TUI=classic`).
