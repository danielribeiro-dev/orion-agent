# Harness de dogfooding (modelo-ponte)

Roda o **ORION real** (sessão, engine, tools, PEP, TUI) num pty, mas o "modelo" é o Claude Code: cada
requisição do ORION vira um arquivo, o Claude Code responde com texto e `tool_use`, e o ORION executa
as tools, mostra os modais e devolve os `tool_result`. Não gasta API (a chave é falsa e nunca enviada).

**Valida:** engine ReAct, schemas, tools, PEP, modais em TTY real, renderer, sessão, contexto, shell em background.
**Não valida:** wire/SSE da Anthropic, prompt caching, thinking e custo reais, nem o comportamento do modelo de produção.

## Uso (feito pelo Claude Code via Bash)
```
python scripts/dogfood/ctl.py start --workspace <dir> [--mcp]   # dir de teste; nunca a raiz do repo na 1ª vez
python scripts/dogfood/ctl.py send "pedido ao ORION"            # digita no prompt
python scripts/dogfood/ctl.py wait                              # imprime o que o ORION pediu ao "modelo"
python scripts/dogfood/ctl.py reply --text "..." --tool read_file '{"path":"a.py"}' [--tool ...]
python scripts/dogfood/ctl.py key y | n | up | down | enter | esc | shift-tab
python scripts/dogfood/ctl.py screen [--full | --tail N]       # o que o Senhor veria
python scripts/dogfood/ctl.py system | tools | status | stop
```
Variável `ORION_DOGFOOD_DIR` (padrão `~/.orion/dogfood/`) guarda `req-*/res-*`, `screen.txt`, `transcript.txt`, `raw.log` e um
`home/` isolado (sessões, ledger, auditoria do ORION de teste). `reply --error MSG` injeta falha do provider.

Requer `pyte` (`pip install -e ".[dogfood]"`). Fica em `scripts/` de propósito: nada em `src/` troca o modelo.
