# Sprint — v0.5.2 Sprint 2: Casco em tela cheia

> **Status:** ✅ Implementada em 16/11/2026 · **ADR:** 043 · **Achados:** N-01 a N-05, N-24 · **CA:** CA-03 a CA-08, CA-11

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

## Registro de implementação (16/11/2026)
- Novos: `tui/screen/{transcript,console,renderer,app,mode,host}.py`; `/tui` em `commands/operation.py` e no catálogo do `completer.py` (31 comandos); `cli.run_fullscreen`; `--fullscreen` no `tests/lab/launcher.py` e `fullscreen=True` no `open_lab`.
- `modal.run_modal`, a edição de comando do PEP, a resposta livre do `ask_user` e o plano delegam ao host ativo.
- Validação visual no `tui-mcp` (110x36 → 72x30): input fixo e vivo durante o turno, fila enviada sozinha ao fim, modal PEP acima do input com status visível, Alt+R abre o raciocínio no lugar, reflow sem régua fantasma, saída com resumo e `--resume`.
- Defeitos achados na validação e corrigidos: negrito do input vazando para a transcrição (`style="nobold"` nas janelas de leitura); raciocínio aberto numa linha só (renderable `Guided` com guia em toda linha quebrada); abrir bloco com a tela rolada contava como "linhas novas" (`Transcript.toggled`); Esc demorava 1 s (`timeoutlen` 0,25 s).
- Testes: `test_screen_transcript.py`, `test_screen_app.py` (teclado simulado), lab `test_fullscreen.py` (4 cenários, incluindo zero escrita ociosa). Lab completo: 25 cenários verdes no modo clássico.
- **Desvio:** a preferência de modo fica em `~/.orion/tui_state.json` (via `/tui`), não em `settings.json` (`ui.tui`), para não mexer no esquema de settings nesta versão.
- **Desvio:** o `attach` do daemon continua no modo clássico (previsto no ADR-043).
