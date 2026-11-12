# Referência de protótipos (v0.5.1)

Código de **apoio à spec**, copiado do scratchpad da sessão de 11/11/2026. **Não é código do produto** e não roda na suíte; serve de ponto de partida para as tarefas indicadas. Ao implementar, reescrever em `tests/lab/` com tipagem, ruff e mypy.

| Arquivo | O que é | Vira |
|:---|:---|:---|
| `lab/launch_scripted.py` | ORION real com `Scripted` provider (streaming com cadência `LAB_CHUNK`/`LAB_DELAY`; cenários por palavra: `longo`, `pensar`, `travar`, `ferramentas`, `erro`) | `tests/lab/scripted_provider.py` (Sprint 1, 1A.2) |
| `lab/probe.py` | Sonda pty + pyte: responde CPR, amostra a tela a cada 20 ms, mede primeiro caractere, duração, atualizações, maior pausa, CPU; cenários `stream typing cancel resize stall think err` | `tests/lab/pty_driver.py` e `probes.py` (1A.1, 1A.3) |
| `lab/sample_workspace_sample.py` | Arquivo de exemplo usado no cenário `ferramentas` (read, edit, run) | fixture do lab |
| `horizon/horizon.py` | Grade de células das telas Horizon (texto, cor, negrito, fundo) com saída ANSI truecolor e JSON | fonte do golden e do mock no Figma (Sprint 2, 2.11 e 2.12) |
| `horizon/build.py`, `horizon/template.html` | Gera a página de prévia a partir da grade | descartável |

## Como rodar (a partir da raiz do repositório, com `.venv/bin` no PATH)
- Caminhos no código apontam para o scratchpad da sessão original (`S = .../scratchpad/lab`): ajustar `S`, `--workspace` e `--home` para diretórios temporários. `HOME` isolado é obrigatório; chave de API é falsa e nunca sai da máquina.
- `python horizon/horizon.py 03-stream` imprime a tela no terminal (use `COLORTERM=truecolor`).
- `python lab/probe.py stream` exige `pyte` (`pip install -e ".[dogfood]"`) e que o modelo de embeddings já esteja em cache no `HOME` de teste (senão o primeiro turno baixa 67 MB: é o V-09).

## Números de referência (110 colunas, ~2,3 mil caracteres a ~200 car/s)
Ver `../achados-tui.md`, tabela "Medições de referência".
