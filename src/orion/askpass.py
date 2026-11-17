"""
O.R.I.O.N — cliente askpass (ADR-048)

Executado pelo ``sudo -A`` (via ``SUDO_ASKPASS``), nunca pelo modelo. Pede a senha ao processo
do ORION por um socket Unix efêmero (0600, ``ORION_ASKPASS_SOCK``) com um token de uso único
(``ORION_ASKPASS_TOKEN``) e a escreve no stdout, que vai direto para o sudo. A senha nunca passa
pelo engine, pelo transcript, pela auditoria nem pelos logs.

Só usa a biblioteca padrão: roda a cada pedido de senha e precisa abrir rápido.
"""

from __future__ import annotations

import json
import os
import socket
import sys

MAX_REPLY = 64 * 1024
TIMEOUT_S = 300.0


def request_secret(sock_path: str, token: str, prompt: str) -> str | None:
    """Pergunta ao broker; devolve a senha ou None (cancelado, negado, sem broker)."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(TIMEOUT_S)
            conn.connect(sock_path)
            conn.sendall(json.dumps({"token": token, "prompt": prompt}).encode() + b"\n")
            data = b""
            while not data.endswith(b"\n") and len(data) < MAX_REPLY:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
    except OSError:
        return None
    try:
        reply = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    secret = reply.get("secret") if isinstance(reply, dict) else None
    return secret if isinstance(secret, str) else None


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    sock_path = os.environ.get("ORION_ASKPASS_SOCK", "")
    token = os.environ.get("ORION_ASKPASS_TOKEN", "")
    if not sock_path or not token:
        sys.stderr.write("orion-askpass: sem sessão do ORION ativa\n")
        return 1
    prompt = args[0] if args else "Senha:"
    secret = request_secret(sock_path, token, prompt)
    if secret is None:
        return 1
    sys.stdout.write(secret + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
