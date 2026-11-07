#!/usr/bin/env python
"""Controle do harness de dogfooding (usado pelo Claude Code via Bash).

  ctl.py start [--workspace P] [--mcp]   sobe o ORION num pty (workspace padrão: cwd)
  ctl.py attach [--workspace P]          modo aba do Senhor: imprime o comando para ele rodar no próprio terminal
  ctl.py wait [--timeout S]              espera a próxima requisição do ORION ao "modelo" e a imprime
  ctl.py reply [--text T] [--tool NOME JSON]... [--error MSG] [--stop-reason R]
  ctl.py send TEXTO [--no-enter]         digita no prompt do ORION
  ctl.py key NOME...                     enter esc up down left right tab shift-tab ctrl-c ctrl-d space bs ou 1 char
  ctl.py screen [--full] [--tail N]      mostra a tela (ou o scrollback inteiro)
  ctl.py system | tools                  system prompt / tools da última requisição
  ctl.py status | stop
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
KEYS = {
    "enter": "\r", "esc": "\x1b", "up": "\x1b[A", "down": "\x1b[B", "right": "\x1b[C", "left": "\x1b[D",
    "tab": "\t", "shift-tab": "\x1b[Z", "ctrl-c": "\x03", "ctrl-d": "\x04", "space": " ", "bs": "\x7f",
}


def bridge_dir() -> Path:
    return Path(os.environ.get("ORION_DOGFOOD_DIR", Path.home() / ".orion" / "dogfood"))


def pending(d: Path) -> int | None:
    for req in sorted(d.glob("req-*.json")):
        n = int(req.stem.split("-")[1])
        if not (d / f"res-{n:04d}.json").exists():
            return n
    return None


def alive(d: Path) -> bool:
    pidfile = d / "driver.pid"
    if not pidfile.exists() or (d / "exit.txt").exists():
        return False
    try:
        os.kill(int(pidfile.read_text()), 0)
        return True
    except (OSError, ValueError):
        return False


def cmd_start(a: argparse.Namespace) -> None:
    d = bridge_dir()
    if alive(d):
        sys.exit(f"já está rodando (dir {d}); use 'stop' antes.")
    for f in d.glob("*"):
        if f.is_file():
            f.unlink()
    d.mkdir(parents=True, exist_ok=True)
    home = d / "home"
    cmd = [
        sys.executable, str(HERE / "driver.py"), "--dir", str(d), "--workspace", str(Path(a.workspace).resolve()),
        "--home", str(home), "--rows", str(a.rows), "--cols", str(a.cols), "--model", a.model,
    ] + (["--mcp"] if a.mcp else [])
    proc = subprocess.Popen(cmd, stdout=open(d / "driver.out", "w"), stderr=subprocess.STDOUT, start_new_session=True)
    (d / "driver.pid").write_text(str(proc.pid))
    for _ in range(100):
        if (d / "screen.txt").exists() and (d / "screen.txt").read_text().strip():
            break
        time.sleep(0.2)
    print(f"ORION no ar (driver pid {proc.pid}, dir {d})")
    cmd_screen(argparse.Namespace(full=False, tail=0))


def cmd_attach(a: argparse.Namespace) -> None:
    """Prepara o diretório e imprime o comando que o Senhor roda na PRÓPRIA aba do terminal."""
    d = bridge_dir()
    if alive(d):
        sys.exit(f"há um ORION ativo em {d}; encerre-o antes.")
    for f in d.glob("*"):
        if f.is_file():
            f.unlink()
    d.mkdir(parents=True, exist_ok=True)
    ws = Path(a.workspace).resolve()
    print("Rode na sua aba do terminal:\n")
    print(f"  python {HERE / 'launch.py'} --bridge {d} --workspace {ws} --home {d / 'home'} --model {a.model}"
          + (" --mcp" if a.mcp else ""))


def cmd_wait(a: argparse.Namespace) -> None:
    d = bridge_dir()
    started = False
    end = time.monotonic() + a.timeout
    while time.monotonic() < end:
        n = pending(d)
        if n is not None:
            print((d / f"req-{n:04d}.txt").read_text(encoding="utf-8"))
            print(f"(responda com: ctl.py reply  -> res-{n:04d})")
            return
        started = started or (d / "driver.pid").exists()
        if started and not alive(d):
            print("ORION encerrou.")
            return
        time.sleep(0.2)
    print("timeout: nenhuma requisição nova.")


def cmd_reply(a: argparse.Namespace) -> None:
    d = bridge_dir()
    n = a.n or pending(d)
    if n is None:
        sys.exit("nenhuma requisição pendente.")
    body: dict[str, object] = {"text": a.text or "", "tools": []}
    for name, raw in a.tool or []:
        try:
            body["tools"].append({"name": name, "input": json.loads(raw)})  # type: ignore[union-attr]
        except json.JSONDecodeError as exc:
            sys.exit(f"JSON inválido para {name}: {exc}")
    if a.error:
        body["error"] = a.error
    if a.stop_reason:
        body["stop_reason"] = a.stop_reason
    tmp = d / f"res-{n:04d}.json.tmp"
    tmp.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    tmp.replace(d / f"res-{n:04d}.json")
    print(f"res-{n:04d} enviada ({len(body['tools'])} tool_use).")  # type: ignore[arg-type]


def push(data: str) -> None:
    with open(bridge_dir() / "keys.in", "ab") as fh:
        fh.write(data.encode())


def cmd_send(a: argparse.Namespace) -> None:
    push(a.text + ("" if a.no_enter else "\r"))
    time.sleep(0.6)
    print("enviado.")


def cmd_key(a: argparse.Namespace) -> None:
    for name in a.keys:
        push(KEYS.get(name, name))
        time.sleep(0.15)
    time.sleep(0.5)
    print("enviado.")


def cmd_screen(a: argparse.Namespace) -> None:
    d = bridge_dir()
    time.sleep(0.3)
    text = (d / ("transcript.txt" if a.full or a.tail else "screen.txt")).read_text(encoding="utf-8")
    if a.tail:
        text = "\n".join(text.rstrip("\n").splitlines()[-a.tail :]) + "\n"
    print(text, end="")


def cmd_show(a: argparse.Namespace) -> None:
    print((bridge_dir() / f"{a.what}.txt").read_text(encoding="utf-8"))


def cmd_status(_: argparse.Namespace) -> None:
    d = bridge_dir()
    print(f"dir={d} vivo={alive(d)} pendente={pending(d)} reqs={len(list(d.glob('req-*.json')))}")


def cmd_stop(_: argparse.Namespace) -> None:
    d = bridge_dir()
    pidfile = d / "driver.pid"
    if pidfile.exists():
        try:
            os.killpg(os.getpgid(int(pidfile.read_text())), signal.SIGTERM)
        except (OSError, ValueError):
            pass
    print("encerrado.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("start")
    p.add_argument("--workspace", default=os.getcwd())
    p.add_argument("--rows", type=int, default=40)
    p.add_argument("--cols", type=int, default=120)
    p.add_argument("--model", default="claude-sonnet-5-5")
    p.add_argument("--mcp", action="store_true")
    p.set_defaults(fn=cmd_start)
    p = sub.add_parser("attach")
    p.add_argument("--workspace", default=os.getcwd())
    p.add_argument("--model", default="claude-sonnet-5-5")
    p.add_argument("--mcp", action="store_true")
    p.set_defaults(fn=cmd_attach)
    p = sub.add_parser("wait")
    p.add_argument("--timeout", type=float, default=120)
    p.set_defaults(fn=cmd_wait)
    p = sub.add_parser("reply")
    p.add_argument("n", nargs="?", type=int)
    p.add_argument("--text", default="")
    p.add_argument("--tool", nargs=2, action="append", metavar=("NOME", "JSON"))
    p.add_argument("--error")
    p.add_argument("--stop-reason")
    p.set_defaults(fn=cmd_reply)
    p = sub.add_parser("send")
    p.add_argument("text")
    p.add_argument("--no-enter", action="store_true")
    p.set_defaults(fn=cmd_send)
    p = sub.add_parser("key")
    p.add_argument("keys", nargs="+")
    p.set_defaults(fn=cmd_key)
    p = sub.add_parser("screen")
    p.add_argument("--full", action="store_true")
    p.add_argument("--tail", type=int, default=0)
    p.set_defaults(fn=cmd_screen)
    for what in ("system", "tools"):
        p = sub.add_parser(what)
        p.set_defaults(fn=cmd_show, what=what)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("stop").set_defaults(fn=cmd_stop)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
