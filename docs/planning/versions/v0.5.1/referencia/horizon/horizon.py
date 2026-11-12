"""Protótipo "Horizon" do ORION: telas como grade de células (texto, fg, bold, bg).

Fonte única: gera ANSI truecolor (para capturar com tui-mcp) e JSON (para montar o Figma).
Não faz parte do repositório; só usa glifos oficiais + ┌ cantos arredondados já permitidos.
"""
from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

C = {
    "bg": "#0B0E14", "panel": "#151B23", "border": "#262F3D",
    "text": "#E6EDF3", "user": "#F0F6FC", "dim": "#8B949E",
    "cyan": "#00D2FF", "blue": "#3A7BD5",
    "add": "#3FB950", "del": "#F85149", "add_t": "#12261C", "del_t": "#2C171B",
    "warn": "#D29922", "ok": "#2EA043", "off": "#DA3633",
    # novos tokens propostos
    "rule": "#566377",      # réguas e guias: visível sem competir com o texto
    "sel": "#1B2634",       # linha selecionada no menu
    "faint": "#7D8590",     # dicas e atalhos (>= 4.5:1 sobre bg)
}

Run = tuple[str, str, bool, str | None]  # texto, fg, bold, bg


def w(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


class Line:
    def __init__(self) -> None:
        self.runs: list[Run] = []

    def add(self, t: str, fg: str = "text", bold: bool = False, bg: str | None = None) -> "Line":
        self.runs.append((t, C[fg] if fg in C else fg, bold, C[bg] if bg in C else bg))
        return self

    def width(self) -> int:
        return sum(w(r[0]) for r in self.runs)


def L(*parts: tuple) -> Line:
    ln = Line()
    for p in parts:
        ln.add(*p)
    return ln


def lerp(a: str, b: str, t: float) -> str:
    x = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    y = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(p + (q - p) * t):02x}" for p, q in zip(x, y))


LOGO = [
    "  ██████╗ ██████╗ ██╗ ██████╗ ███╗   ██╗",
    " ██╔═══██╗██╔══██╗██║██╔═══██╗████╗  ██║",
    " ██║   ██║██████╔╝██║██║   ██║██╔██╗ ██║",
    " ██║   ██║██╔══██╗██║██║   ██║██║╚██╗██║",
    " ╚██████╔╝██║  ██║██║╚██████╔╝██║ ╚████║",
    "  ╚═════╝ ╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═╝  ╚═══╝",
]


def rule(cols: int, fg: str = "rule") -> Line:
    return L(("─" * cols, fg))


def prompt_block(cols: int, text: str = "", placeholder: bool = True, mode: str = "accept-edits",
                 state: str = "Ready", dot: str = "ok") -> list[Line]:
    body = L(("❯ ", "cyan", True))
    if text:
        body.add(text, "user", True)
    elif placeholder:
        body.add("digite sua instrução…", "faint")
    sep = (" · ", "faint")
    status = L((mode, "blue", True), sep, ("claude-sonnet-5-5", "dim"), sep,
               ("24% ctx", "dim"), sep, ("$0.088", "dim"), sep, ("PEP 2", "warn"), sep,
               (state + " ", "dim"), ("●", dot))
    return [rule(cols), body, rule(cols), status]


def splash(cols: int = 110) -> list[Line]:
    out: list[Line] = [L()]
    info: list[Line | None] = [
        None,
        L(("  O.R.I.O.N", "cyan", True), ("  v0.5.0", "dim"), ("  ·  ", "faint"), ("Non Ducor, Duco", "dim")),
        L(("  Operational Reasoning & Intelligence Orchestration Network", "dim")),
        None,
        L(("  ●", "ok"), (" online", "text"), ("  ·  ", "faint"), ("claude-sonnet-5-5", "text"),
          ("  ·  ", "faint"), ("~/orion-agent", "dim")),
        L(("  PEP 2 supervisionado", "warn"), ("  ·  ", "faint"), ("memória 5 esferas", "dim"),
          ("  ·  ", "faint"), ("github", "dim")),
    ]
    for i, art in enumerate(LOGO):
        ln = L((art, lerp(C["cyan"], C["blue"], i / 5), True))
        if cols >= 100 and info[i] is not None:
            ln.runs += info[i].runs  # type: ignore[union-attr]
        out.append(ln)
    if cols < 100:
        out.append(L(("  O.R.I.O.N", "cyan", True), ("  v0.5.0", "dim"), ("  ·  ", "faint"), ("Non Ducor, Duco", "dim")))
        out.append(L(("  ●", "ok"), (" online", "text"), ("  ·  ", "faint"), ("claude-sonnet-5-5", "text")))
        out.append(L(("  PEP 2", "warn"), ("  ·  ", "faint"), ("memória 5 esferas", "dim")))
    out.append(L())
    tip = L(("  ", "dim"), ("/", "cyan"), (" comandos", "dim"), ("  ·  ", "faint"), ("@", "cyan"),
            (" arquivos", "dim"), ("  ·  ", "faint"), ("Shift+Tab", "text"), (" modo", "dim"),
            *((("  ·  ", "faint"), ("Alt+T", "text"), (" raciocínio", "dim")) if cols >= 100 else ()),
            ("  ·  ", "faint"), ("Ctrl+C", "text"), (" ×2 sai", "dim"))
    out.append(tip)
    out.append(L())
    out += prompt_block(cols)
    return out


COMMANDS = [
    ("/plan", "Gerar plano estruturado antes de implementar", "cognitivo"),
    ("/goal", "Execução autônoma contínua até concluir", "cognitivo"),
    ("/review", "Revisão crítica dos diffs recentes", "cognitivo"),
    ("/diff", "Alterações pendentes no workspace", "operação"),
    ("/undo", "Reverter última alteração", "operação"),
    ("/cost", "Custos e consumo acumulado (USD/BRL)", "operação"),
    ("/context", "Composição da janela de contexto", "contexto"),
    ("/compact", "Compactar contexto preservando a cauda vital", "contexto"),
]


def autocomplete(cols: int = 110, sel: int = 0) -> list[Line]:
    out: list[Line] = [L(("  ", "dim"), ("/", "cyan"), (" comandos", "dim"), ("  ·  ", "faint"), ("@", "cyan"),
                         (" arquivos", "dim")), L()]
    mw = 78
    for i, (name, desc, cat) in enumerate(COMMANDS):
        bg = "sel" if i == sel else "panel"
        ln = Line()
        if i == sel:
            ln.add(" ❯ ", "cyan", True, bg).add(f"{name:<10}", "cyan", True, bg).add(f"{desc:<{mw - 13 - 11}}", "text", False, bg)
        else:
            ln.add("   ", "dim", False, bg).add(f"{name:<10}", "text", False, bg).add(f"{desc:<{mw - 13 - 11}}", "dim", False, bg)
        ln.add(f"{cat:>9}", "dim" if i == sel else "faint", False, bg).add(" ", "dim", False, bg)
        out.append(ln)
    out.append(L((f" ↑↓ navegar  ·  Tab aceitar  ·  Esc fechar{'':<{mw - 51}}", "faint", False, "panel"),
                 (f"{sel + 1}/23 ", "faint", False, "panel")))
    out += prompt_block(cols, text="/", mode="accept-edits")
    return out


def stream(cols: int = 110) -> list[Line]:
    o: list[Line] = []
    o.append(L(("❯ ", "cyan", True), ("adicione o streaming ao vivo sem quebrar a rolagem do terminal", "user", True)))
    o.append(L())
    o.append(L(("▼ ", "blue"), ("Raciocínio · 4,1s", "dim"), ("   Alt+R expande", "faint")))
    o.append(L())
    o.append(L(("Vou trocar a impressão direta por ", "text"), ("Rich.Live", "cyan"), (" no ", "text"),
               ("StreamRenderer", "blue"), (", mantendo a saída em stdout contínuo.", "text")))
    o.append(L())
    o.append(L(("✔ ", "ok"), ("Read", "text", True), ("  src/orion/tui/stream_renderer.py", "dim"), ("  ·  0,1s", "faint")))
    o.append(L(("  › ", "faint"), ("212 linhas", "dim")))
    o.append(L(("✔ ", "ok"), ("Edit", "text", True), ("  src/orion/tui/stream_renderer.py", "dim"), ("  ·  0,2s", "faint")))
    o.append(L(("  › ", "faint"), ("+6 ", "add"), ("−3", "del")))
    # painel de diff
    pw = cols
    title = " src/orion/tui/stream_renderer.py  "
    o.append(L(("╭─", "rule"), (title, "text", True), ("+6", "add", True), (" ", "dim"), ("−3 ", "del", True),
               ("─" * (pw - 2 - len(title) - 7), "rule"), ("╮", "rule")))

    def d(kind: str, ln_a: str, ln_b: str, code: str) -> Line:
        bg = {"add": "add_t", "del": "del_t", "ctx": None}[kind]
        sign = {"add": "+", "del": "−", "ctx": " "}[kind]
        sfg = {"add": "add", "del": "del", "ctx": "faint"}[kind]
        inner = pw - 2
        code_txt = f" {code}"
        pad = inner - 4 - 4 - 3 - len(code_txt)
        return (L(("│", "rule"))
                .add(f"{ln_a:>4}", "faint", False, bg).add(f"{ln_b:>4}", "faint", False, bg)
                .add(f" {sign} ", sfg, True, bg).add(code_txt + " " * pad, "text", False, bg).add("│", "rule"))

    def hunk(t: str) -> Line:
        return L(("│", "rule"), (f" {t}", "blue"), (" " * (pw - 3 - len(t)), "dim"), ("│", "rule"))

    o.append(hunk("@@ -41,5 +41,8 @@ class StreamRenderer"))
    o.append(d("ctx", "41", "41", "async def consume(self, tokens: AsyncIterator[str]) -> None:"))
    o.append(d("del", "42", "", '    buffer = ""'))
    o.append(d("del", "43", "", "    async for token in tokens:"))
    o.append(d("add", "", "42", "    self._buffer = StringIO()"))
    o.append(d("add", "", "43", "    with Live(console=self.console, refresh_per_second=12) as live:"))
    o.append(d("add", "", "44", "        async for token in tokens:"))
    o.append(L(("╰", "rule"), ("─" * (pw - 2), "rule"), ("╯", "rule")))
    o.append(L(("✔ ", "ok"), ("Bash", "text", True), ("  pytest tests/unit/test_stream_renderer.py", "dim"), ("  ·  1,4s  ·  exit 0", "faint")))
    for t in ("============ test session starts ============", "collected 14 items"):
        o.append(L(("  │ ", "rule"), (t, "dim")))
    o.append(L(("  │ ", "rule"), ("+9 linhas ocultas", "blue"), ("  ·  Alt+E expande", "faint")))
    o.append(L(("  │ ", "rule"), ("======= 14 passed in 1.38s =======", "dim")))
    o.append(L())
    o.append(L(("Pronto.", "text", True)))
    o.append(L(("· ", "cyan"), ("consume()", "cyan"), (" agora atualiza o Markdown a cada token, 12 vezes por segundo.", "text")))
    o.append(L())
    o.append(L(("⠋ ", "cyan"), ("Bash", "text", True), ("  ruff check src/orion/tui", "dim"), ("  ·  3s  ·  ", "faint"), ("Ctrl+C cancela", "faint")))
    o.append(L())
    o += prompt_block(cols, state="Working", dot="cyan")
    return o


def pep(cols: int = 110) -> list[Line]:
    o: list[Line] = []
    o.append(L(("⠋ ", "cyan"), ("Bash", "text", True), ("  git push origin main", "dim"), ("  ·  aguardando autorização", "faint")))
    o.append(L())
    t = " [PEP 2] Autorização requerida "
    o.append(L(("╭─", "warn"), (t, "warn", True), ("─" * (cols - 2 - len(t) - 1), "warn"), ("╮", "warn")))

    def row(k: str, v: str, vfg: str = "text") -> Line:
        pad = cols - 2 - 2 - 12 - len(v)
        return L(("│", "warn"), ("  ", "dim"), (f"{k:<12}", "dim"), (v, vfg), (" " * pad, "dim"), ("│", "warn"))

    o.append(row("Ação", "Executar comando no sistema operacional"))
    o.append(row("Comando", "git push origin main", "cyan"))
    o.append(row("Impacto", "Atualiza o repositório remoto com os commits locais"))
    o.append(L(("╰", "warn"), ("─" * (cols - 2), "warn"), ("╯", "warn")))
    o.append(L(("  ", "dim"), ("y", "add", True), (" aprovar", "dim"), ("   ", "dim"), ("n", "del", True), (" negar", "dim"),
               ("   ", "dim"), ("e", "text", True), (" editar", "dim"), ("   ", "dim"), ("a", "text", True),
               (" sempre nesta sessão", "dim"), ("   ", "dim"), ("Esc", "text", True), (" cancela", "dim")))
    o.append(L())
    o += prompt_block(cols, state="Aguardando", dot="warn")
    return o


SCREENS = {
    "01-splash-110": lambda: splash(110),
    "01b-splash-80": lambda: splash(80),
    "02-autocomplete": lambda: autocomplete(110, 1),
    "03-stream": lambda: stream(110),
    "04-pep": lambda: pep(110),
}


def to_ansi(lines: list[Line], cols: int) -> str:
    def esc(hexv: str, bg: bool) -> str:
        r, g, b = (int(hexv[i:i + 2], 16) for i in (1, 3, 5))
        return f"\x1b[{48 if bg else 38};2;{r};{g};{b}m"

    out = []
    for ln in lines:
        s = ""
        for t, fg, bold, bg in ln.runs:
            s += esc(bg or C["bg"], True) + esc(fg, False) + ("\x1b[1m" if bold else "\x1b[22m") + t
        pad = cols - ln.width()
        s += esc(C["bg"], True) + " " * max(pad, 0) + "\x1b[0m"
        out.append(s)
    return "\n".join(out)


if __name__ == "__main__":
    name = sys.argv[1]
    cols = 80 if name.endswith("80") else 110
    sys.stdout.write("\x1b[2J\x1b[H" + to_ansi(SCREENS[name](), cols) + "\n")
    if len(sys.argv) > 2:
        data = {k: [[list(r) for r in ln.runs] for ln in fn()] for k, fn in SCREENS.items()}
        Path(sys.argv[2]).write_text(json.dumps(data, ensure_ascii=False))
