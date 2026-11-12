"""Sonda de TUI: roda o ORION (provider roteirizado) num pty, amostra a tela a cada ~20 ms e mede."""
import fcntl, hashlib, json, os, pty, select, signal, struct, sys, termios, time
import pyte

SC = sys.argv[1]; COLS, ROWS = 110, 36
S = os.path.dirname(os.path.abspath(__file__))
env = dict(os.environ, HOME=f"{S}/home", COLORTERM="truecolor", TERM="xterm-256color", LAB_CHUNK="6", LAB_DELAY="0.03")
pid, fd = pty.fork()
if pid == 0:
    os.chdir(f"{S}/ws")
    os.execve("/home/danieldev/orion-agent/.venv/bin/python", ["python", f"{S}/launch_scripted.py", "--workspace", f"{S}/ws", "--home", f"{S}/home"], env)
def setsize(c, r):
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", r, c, 0, 0))
setsize(COLS, ROWS)
screen = pyte.HistoryScreen(COLS, ROWS, history=2000); stream = pyte.Stream(screen)
t0 = time.time(); tl = []  # (t, hash)
def cpu():
    try:
        f = open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split(); return (int(f[11]) + int(f[12])) / os.sysconf("SC_CLK_TCK")
    except Exception: return 0.0
def disp(): return "\n".join(l.rstrip() for l in screen.display)
def pump(dur):
    end = time.time() + dur
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.02)
        if r:
            try: d = os.read(fd, 65536)
            except OSError: return
            stream.feed(d.decode("utf-8", "replace"))
            if b"[6n" in d: os.write(fd, f"[{screen.cursor.y+1};{screen.cursor.x+1}R".encode())
            tl.append((time.time() - t0, hashlib.md5(disp().encode()).hexdigest()[:8]))
def wait(pat, to=60):
    end = time.time() + to
    while time.time() < end:
        pump(0.1)
        if pat in disp(): return time.time() - t0
    return None
def send(s): os.write(fd, s.encode())
ev = {}
ev["boot"] = wait("❯", 70)
if ev["boot"] is None: print("boot falhou"); print(disp()); os.kill(pid, 9); sys.exit(1)
pump(1.0)
def turn(msg, ready_pat="Ready"):
    global tl
    tl = []; base = time.time(); c0 = cpu()
    send(msg + "\r"); ts = time.time()
    return ts, c0
ts, c0 = turn(SC_MSG := {"stream": "texto longo", "typing": "texto longo", "cancel": "texto longo", "resize": "texto longo", "stall": "travar agora", "think": "pensar bem", "err": "gerar erro"}[SC])
mark = {}
first_char_pat = {"stall": "Resposta que", "think": "Depois de pensar", "err": "falha simulada"}.get(SC, "Análise")
if SC in ("typing", "cancel", "resize"):
    ev["first"] = wait(first_char_pat, 30); pump(1.2)
    if SC == "typing": send("abc"); mark["typed_at"] = time.time() - t0; pump(2.0); mark["abc_on_screen_during_stream"] = "abc" in disp()
    if SC == "cancel": send("\x03"); mark["ctrl_c_at"] = time.time() - t0
    if SC == "resize": setsize(80, 30); os.kill(pid, signal.SIGWINCH); screen.resize(30, 80); mark["resize_at"] = time.time() - t0; pump(2.0)
else:
    ev["first"] = wait(first_char_pat, 30)
done = wait("Ready ●", 60) if SC != "stall" else None
if SC == "stall":
    # durante a pausa de 6s: a tela muda (spinner/cronômetro)?
    tl2_start = len(tl); pump(7.0); mark["screen_changes_during_6s_stall"] = len({h for _, h in tl[tl2_start:]})
    done = wait("Ready ●", 30)
if SC == "typing" and done: mark["abc_after_ready_in_prompt"] = "❯ abc" in disp()
pump(1.0)
ends = time.time() - t0
changes = [t for i, (t, h) in enumerate(tl) if i == 0 or h != tl[i-1][1]]
gaps = [b - a for a, b in zip(changes, changes[1:])]
m = {"scenario": SC, "ttfc_s": round(ev["first"] - (ts - t0), 2) if ev.get("first") else None,
     "total_s": round((done or ends) - (ts - t0), 2) if done else None, "screen_updates": len(changes),
     "max_gap_s": round(max(gaps), 2) if gaps else None, "gaps_over_300ms": sum(g > 0.3 for g in gaps),
     "cpu_s": round(cpu() - c0, 2), **mark}
print(json.dumps(m, ensure_ascii=False))
open(f"{S}/out-{SC}.txt", "w").write("\n".join([*[ "".join(l[x].data for x in range(screen.columns)).rstrip() for l in screen.history.top], disp()]))
os.kill(pid, 9)
