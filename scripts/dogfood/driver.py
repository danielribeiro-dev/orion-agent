"""Hospeda o ORION num pty: emula o terminal (pyte), grava a tela e injeta teclas vindas de keys.in."""

from __future__ import annotations

import argparse
import fcntl
import os
import pty
import select
import struct
import sys
import termios
import time
from pathlib import Path

import pyte


def render(screen: pyte.HistoryScreen, cols: int) -> tuple[str, str]:
    def row(line: object) -> str:
        return "".join(line[x].data for x in range(cols)).rstrip()  # type: ignore[index]

    visible = [line.rstrip() for line in screen.display]
    while visible and not visible[-1]:
        visible.pop()
    history = [row(line) for line in screen.history.top]
    return "\n".join(visible) + "\n", "\n".join([*history, *visible]) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--home", required=True)
    ap.add_argument("--rows", type=int, default=40)
    ap.add_argument("--cols", type=int, default=120)
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--mcp", action="store_true")
    args = ap.parse_args()
    work = Path(args.dir)
    work.mkdir(parents=True, exist_ok=True)
    keys = work / "keys.in"
    keys.write_bytes(b"")

    cmd = [
        sys.executable, str(Path(__file__).parent / "launch.py"),
        "--bridge", str(work), "--workspace", args.workspace, "--home", args.home, "--model", args.model,
    ] + (["--mcp"] if args.mcp else [])
    pid, fd = pty.fork()
    if pid == 0:
        os.environ.update(TERM="xterm-256color", COLUMNS=str(args.cols), LINES=str(args.rows))
        os.execv(sys.executable, cmd)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", args.rows, args.cols, 0, 0))

    screen = pyte.HistoryScreen(args.cols, args.rows, history=5000, ratio=1.0)
    screen.write_process_input = lambda data: os.write(fd, data.encode())  # responde CPR (ESC[6n)
    stream = pyte.ByteStream(screen)
    raw = open(work / "raw.log", "ab")
    offset, last_dump, dirty = 0, 0.0, True
    exit_code: int | None = None
    while True:
        ready, _, _ = select.select([fd], [], [], 0.1)
        if ready:
            try:
                data = os.read(fd, 65536)
            except OSError:
                data = b""
            if not data:
                break
            raw.write(data)
            raw.flush()
            stream.feed(data)
            dirty = True
        blob = keys.read_bytes()
        if len(blob) > offset:
            os.write(fd, blob[offset:])
            offset = len(blob)
        if dirty and time.monotonic() - last_dump > 0.1:
            view, full = render(screen, args.cols)
            (work / "screen.tmp").write_text(view, encoding="utf-8")
            (work / "screen.tmp").replace(work / "screen.txt")
            (work / "transcript.txt").write_text(full, encoding="utf-8")
            last_dump, dirty = time.monotonic(), False
    try:
        _, status = os.waitpid(pid, 0)
        exit_code = os.waitstatus_to_exitcode(status)
    except ChildProcessError:
        pass
    view, full = render(screen, args.cols)
    (work / "screen.txt").write_text(view, encoding="utf-8")
    (work / "transcript.txt").write_text(full, encoding="utf-8")
    (work / "exit.txt").write_text(f"{exit_code}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
