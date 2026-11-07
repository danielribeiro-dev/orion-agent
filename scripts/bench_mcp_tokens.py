# ruff: noqa: E701, E702, E741  (throwaway benchmark script, compact on purpose)
import asyncio
import json
import pathlib
import subprocess

from orion.mcp.adapter import build_adapters, catalog_lines
from orion.mcp.client import MCPClient, load_server_configs
from orion.tui.session import TOOL_PROTOCOL


def tok(s): return max(1, len(s) // 4)   # same 4 chars/token heuristic ORION uses
def sh(cmd): return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout
def read(p): return pathlib.Path(p).read_text()

async def mcp(c, tool, **a):
    ok, text = await c.call_tool("serena", tool, a)
    return text if ok else f"[ERR] {text}"

async def main():
    cfgs = load_server_configs(None, None)
    c = MCPClient({"serena": cfgs["serena"], "context7": cfgs["context7"]}, connect_timeout=240); await c.start()
    ad = build_adapters(c)
    # ---- prompt overhead ----
    full = sum(len(json.dumps(a.schema())) + len(a.definition.description) for a in ad.values())
    lazy = sum(len(l) for l in catalog_lines(ad))
    print(f"[overhead] visible MCP tools={len(ad)} | full-schema ~{full//4} tok | lazy catalog ~{lazy//4} tok | base TOOL_PROTOCOL ~{len(TOOL_PROTOCOL)//4} tok")
    rows = []
    # T1: definition + callers of PolicyEnforcementPoint.evaluate
    base = sh('grep -rn "evaluate(" src') + read("src/orion/governance/pep.py")
    ser = await mcp(c, "find_symbol", name_path_pattern="PolicyEnforcementPoint/evaluate", relative_path="src/orion/governance/pep.py", include_body=True) \
        + await mcp(c, "find_referencing_symbols", name_path="PolicyEnforcementPoint/evaluate", relative_path="src/orion/governance/pep.py")
    rows.append(("T1 definição+callers de PEP.evaluate", tok(base), tok(ser), ser))
    # T2: structure of a big file
    base = read("src/orion/tui/session.py")
    ser = await mcp(c, "get_symbols_overview", relative_path="src/orion/tui/session.py", depth=1)
    rows.append(("T2 estrutura de tui/session.py", tok(base), tok(ser), ser))
    # T3: usages of a function
    base = sh('grep -rn "tool_action_level" src')
    ser = await mcp(c, "find_referencing_symbols", name_path="tool_action_level", relative_path="src/orion/governance/permissions.py")
    rows.append(("T3 usos de tool_action_level", tok(base), tok(ser), ser))
    # T4: read one method body
    base = read("src/orion/mcp/client.py")
    ser = await mcp(c, "find_symbol", name_path_pattern="MCPClient/call_tool", relative_path="src/orion/mcp/client.py", include_body=True)
    rows.append(("T4 corpo de MCPClient.call_tool", tok(base), tok(ser), ser))
    print(f"{'tarefa':42}{'nativo(tok)':>13}{'serena(tok)':>13}{'economia':>10}")
    for n, b, s, txt in rows:
        err = " [ERR]" if txt.startswith("[ERR]") or "error" in txt[:80].lower() else ""
        print(f"{n:42}{b:>13}{s:>13}{(1-s/b)*100:>9.0f}%{err}")
    tb, ts = sum(r[1] for r in rows), sum(r[2] for r in rows)
    print(f"{'TOTAL':42}{tb:>13}{ts:>13}{(1-ts/tb)*100:>9.0f}%")
    for n, _, _, txt in rows: print("--", n, "->", txt[:160].replace("\n", " "))
    await c.close()
asyncio.run(main())
