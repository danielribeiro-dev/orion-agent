#!/usr/bin/env sh
# Instala o O.R.I.O.N fora da venv (ADR-044).
#   scripts/install.sh          instala este checkout como versão fixa
#   scripts/install.sh --dev    instalação editável (o comando segue o código do repositório)
# Resultado: ~/.local/share/orion/current e os atalhos ~/.local/bin/orion e orion-agent.
set -eu
SRC=$(cd "$(dirname "$0")/.." && pwd)
PY=${PYTHON:-python3}
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    echo "✖ o O.R.I.O.N exige Python 3.11 ou mais novo ($PY)" >&2
    exit 1
fi
PYTHONPATH="$SRC/src" exec "$PY" -m orion.install --source "$SRC" "$@"
