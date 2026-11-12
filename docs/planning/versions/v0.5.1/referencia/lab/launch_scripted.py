"""ORION real com provider roteirizado (streaming com cadência realista). Fora do repositório; custo zero."""
from __future__ import annotations
import argparse, asyncio, os, sys
from collections.abc import AsyncIterator
from pathlib import Path

from orion.gateway.models import ContentBlock, LLMRequest, LLMResponse, LLMResponseChunk, TokenUsage
from orion.gateway.providers.base import BaseLLMProvider

CPS_CHUNK = int(os.environ.get("LAB_CHUNK", "6"))      # caracteres por evento SSE
CPS_DELAY = float(os.environ.get("LAB_DELAY", "0.03"))  # segundos entre eventos (~200 car/s)

LONG = """## Análise do módulo de streaming

O renderer atual **imprime cada token** direto em stdout, o que quebra a rolagem nativa quando a resposta passa de uma tela. A proposta é manter um buffer e atualizar o Markdown em intervalos fixos.

### Pontos principais

- `StreamRenderer.consume()` acumula os tokens em um buffer
- A atualização acontece 12 vezes por segundo, não a cada token
- O histórico permanece na rolagem nativa do terminal
- Blocos de código só são realçados quando fecham

### Exemplo

```python
async def consume(self, tokens):
    buffer = StringIO()
    with Live(console=self.console, refresh_per_second=12, transient=False) as live:
        async for token in tokens:
            buffer.write(token)
            live.update(Markdown(buffer.getvalue()))
```

| Estratégia | Latência | Rolagem |
| :--- | :--- | :--- |
| print direto | baixa | quebra |
| Live 12 Hz | média | preserva |
| Live 30 Hz | baixa | preserva, mais CPU |

Em resumo: o custo de CPU cresce com o tamanho do buffer, então vale **limitar a janela viva** às últimas linhas e despejar o restante no histórico. Isso evita o flicker visto em respostas longas e mantém a digitação fluida durante o streaming. """ * 2

def last_user_text(req):
    for m in reversed(req.messages):
        c = m.content
        if isinstance(c, str):
            if m.role.value == "user": return c
        else:
            t = " ".join(b.text or "" for b in c if b.type == "text")
            if m.role.value == "user" and t.strip(): return t
    return ""

def tool_stage(req):
    n = 0
    for m in reversed(req.messages):
        c = m.content
        if not isinstance(c, str) and any(b.type == "tool_result" for b in c): n += 1
        elif m.role.value == "user": break
    return n

class Scripted(BaseLLMProvider):
    provider_name = "scripted"
    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError
    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMResponseChunk]:  # type: ignore[override]
        txt = last_user_text(request).lower()
        stage = tool_stage(request)
        text, tools, reasoning, stall = "", [], "", False
        if "erro" in txt:
            await asyncio.sleep(0.4); raise RuntimeError("falha simulada do provedor (lab)")
        if "longo" in txt: text = LONG
        elif "pensar" in txt: reasoning = "Preciso comparar as duas abordagens. " * 12; text = "Depois de pensar: prefira o buffer com atualização em intervalo fixo."
        elif "travar" in txt: text = "Resposta que trava no meio do stream. " * 6; stall = True
        elif "ferramentas" in txt:
            if stage == 0: text = "Vou ler o arquivo antes de editar."; tools = [("read_file", {"path": "sample.py"})]
            elif stage == 1: text = "Agora troco a saudação."; tools = [("edit_file", {"path": "sample.py", "target": 'print("ola", name)', "replacement": 'print(f"Olá, {name}!")'})]
            elif stage == 2: text = "Rodo o arquivo e uma contagem longa."; tools = [("run_command", {"command": "python sample.py Senhor && seq 1 40"})]
            else: text = "Feito. O arquivo foi lido, editado e executado; a contagem terminou em 40."
        else: text = "pong"
        if reasoning:
            for i in range(0, len(reasoning), CPS_CHUNK):
                yield LLMResponseChunk(reasoning_delta=reasoning[i:i+CPS_CHUNK]); await asyncio.sleep(CPS_DELAY)
        half = len(text) // 2
        for i in range(0, len(text), CPS_CHUNK):
            yield LLMResponseChunk(delta=text[i:i+CPS_CHUNK])
            if stall and i >= half and i < half + CPS_CHUNK: await asyncio.sleep(6)
            await asyncio.sleep(CPS_DELAY)
        if text: yield LLMResponseChunk(block=ContentBlock.of_text(text))
        for i, (name, inp) in enumerate(tools, 1):
            yield LLMResponseChunk(block=ContentBlock.of_tool_use(f"toolu_lab_{stage}_{i}", name, inp))
        yield LLMResponseChunk(is_final=True, stop_reason="tool_use" if tools else "end_turn",
                               usage=TokenUsage(prompt_tokens=1200, completion_tokens=max(1, len(text)//4)))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workspace", required=True); ap.add_argument("--home", required=True)
    a = ap.parse_args()
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-lab-dummy-never-sent"; os.environ["ORION_MCP"] = "0"
    os.chdir(a.workspace)
    from orion import cli
    from orion.tui.session import AgentSession
    from orion.tui.status_bar import SessionStatusBar
    home = Path(a.home); cli.configure_logging(home)
    provider = Scripted(); sb = SessionStatusBar.from_environment()
    session = AgentSession(status_bar=sb, console=cli.console, workspace=Path(a.workspace), home=home, provider_factory=lambda spec: provider)
    session.set_model("claude-sonnet-5-5")
    if cli.console.is_terminal: cli.console.clear()
    lines = cli.print_banner(sb); prompt = cli.create_prompt(sb, session); prompt.dock_to_bottom(lines)
    cli.run_interactive_repl(prompt, session)

if __name__ == "__main__": main()
