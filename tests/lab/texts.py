"""Textos dos roteiros do laboratório (respostas "do modelo")."""

from __future__ import annotations

_LONG_PART = """## Análise do módulo de streaming

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

Em resumo: o custo de CPU cresce com o tamanho do buffer, então vale **limitar a janela viva** às últimas linhas e despejar o restante no histórico.

"""

LONG = _LONG_PART + _LONG_PART.replace("## Análise", "## Segunda análise").replace(
    "Em resumo:", "Fim da resposta longa:"
)
"""Resposta de ~2,3 mil caracteres com títulos, lista, código e tabela."""

CODE_TALL = (
    "Segue o arquivo inteiro:\n\n```python\n"
    + "\n".join(f"linha_{n:02d} = {n}  # valor da linha {n}" for n in range(1, 41))
    + "\n```\n\nFim do arquivo.\n"
)
"""Bloco de código de 40 linhas: mais alto que um terminal de 24 linhas (V-10)."""

STALL = "Resposta que pausa no meio do stream. " * 6
