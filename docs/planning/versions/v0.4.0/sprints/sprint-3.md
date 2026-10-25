# Sprint — [v0.4.0] Sprint 3: Streaming Vivo, Diffs & Catálogo de Slash Commands

> **Status:** 📋 Planejado  
> **Versão Relacionada:** v0.4.0 (High-Performance Stream CLI, Slash Commands & Native MCP)  
> **Responsável / Agente:** Daniel Dev & Antigravity  
> **Data de Início:** A definir (Fase 4)  
> **Data de Conclusão:** —  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Implementar o renderizador de streaming em tempo real via `Rich.Live` (garantindo que as respostas do modelo fluam em Markdown renderizado com realce sintático sem quebrar o scroll nativo do terminal), o visualizador de **diffs cirúrgicos** formatados em caixas Rich com realce verde/vermelho para arquivos editados, e o despachante e catálogo completo dos **20 Slash Commands oficiais** do O.R.I.O.N.
* **Dependências Prévias:** Sprint 1 e 2 concluídas (CLI Skeleton, Banner e Prompt Interativo operacionais).
* **Entregável Verificável:** Módulos `src/orion/tui/stream_renderer.py`, `src/orion/tui/diff_viewer.py` e pacote `src/orion/tui/commands/` totalmente funcionais, permitindo interagir com streaming vivo, ver alterações em diffs elegantes e disparar comandos rápidos.

---

## 2. Contexto de Engenharia

* **Por que esta sprint existe:** Respostas de IA não podem ser dumps estáticos que travam o terminal por 10 segundos antes de exibir uma parede de texto. O desenvolvedor precisa ver o raciocínio e o código surgindo em tempo real. Além disso, ver diffs claros com cores antes de aceitar alterações é a maior garantia de segurança e controle em agentes modernos.
* **Como se encaixa na visão global:** Entrega o núcleo da interação ativa do assistente, transformando o `orion-agent` em uma ferramenta prazerosa, estética e com comandos profissionais.
* **Decisões arquiteturais associadas:** ADR-015 (Stack Stream CLI com `Rich.Live`), ADR-016 (Catálogo Oficial de Slash Commands).

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Estado Inicial (Antes da Sprint) | Estado Final Esperado (DoD) |
| :--- | :--- | :--- |
| **Streaming de Texto** | Impressão básica em blocos | `Rich.Live` com parsing de Markdown contínuo e realce sintático |
| **Exibição de Diffs** | Texto unificado puro no terminal | Painéis Rich elegantes com destaque visual de adições e remoções |
| **Slash Commands** | Apenas suporte básico | Catálogo modular completo com 20 comandos cadastrados e tipados |

---

## 4. Escopo da Sprint

### ✅ No Escopo (In Scope)
- [ ] Implementação de `StreamRenderer` em `src/orion/tui/stream_renderer.py`:
  - Consumo assíncrono do gerador de tokens do ReAct Engine.
  - Renderização via `rich.live.Live` sem buffers travados de tela cheia, preservando a rolagem natural do mouse/trackpad.
  - Exibição de indicador de pensamento (*thinking spinner*) enquanto o raciocínio é formulado.
- [ ] Implementação de `DiffViewer` em `src/orion/tui/diff_viewer.py`:
  - Conversão de diffs unificados gerados por `edit_file` em painéis Rich formatados.
  - Números de linha originais e novas, cabeçalho com nome do arquivo e resumo de adições/remoções (`+X / -Y`).
- [ ] Implementação da arquitetura de comandos em `src/orion/tui/commands/`:
  - `BaseSlashCommand`: contrato com `name`, `description`, `usage` e método assíncrono `execute(args, context)`.
  - `CommandRegistry`: descoberta automática e despacho determinístico.
  - Implementação dos 20 comandos:
    - Cognitivos: `/plan`, `/goal`, `/grill-me`, `/review`
    - Memória & Skills: `/learn`, `/memory`, `/timeline`, `/recall`
    - Contexto & Branches: `/compact`, `/context`, `/branch`, `/merge`
    - Operação & Governança: `/diff`, `/undo`, `/run`, `/doctor`, `/cost`, `/config`, `/clear`, `/help`
- [ ] Testes unitários do despachante de comandos e dos componentes de streaming e diffs.

### 🚫 Fora de Escopo (Out of Scope / Anti-Metas)
- Não construir conexões MCP nativas com transporte SSE/stdio (escopo da Sprint 4).

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/tui/
├── stream_renderer.py                 # Renderizador de streaming Markdown (Rich.Live)
├── diff_viewer.py                     # Visualizador de diffs cirúrgicos
└── commands/                          # Catálogo oficial de comandos
    ├── __init__.py
    ├── base.py                        # BaseSlashCommand
    ├── registry.py                    # CommandRegistry central
    ├── plan.py
    ├── goal.py
    ├── grill_me.py
    ├── review.py
    ├── learn.py
    ├── memory.py
    ├── timeline.py
    ├── compact.py
    ├── context.py
    ├── branch.py
    ├── diff.py
    ├── cost.py
    ├── doctor.py
    └── help.py
tests/
└── unit/
    ├── test_stream_renderer.py
    ├── test_diff_viewer.py
    └── test_slash_commands.py
```

---

## 6. Contratos de Código & Tipagem

```python
from abc import ABC, abstractmethod
from typing import Any, List
from pydantic import BaseModel

class CommandResult(BaseModel):
    success: bool
    output_message: str
    data: Any = None

class BaseSlashCommand(ABC):
    name: str
    description: str
    usage: str = ""
    aliases: List[str] = []

    @abstractmethod
    async def execute(self, args: str, context: Any) -> CommandResult:
        """Executa a rotina do comando slash e retorna o resultado formatado."""
        pass
```

---

## 7. Estratégia de Implementação (Passo a Passo)

1. **Passo 1:** Desenvolver `StreamRenderer` com `Rich.Live` e buffer dinâmico de tokens.
2. **Passo 2:** Desenvolver `DiffViewer` tratando blocos de diff `@@ -A,B +C,D @@` com sintaxe colorida.
3. **Passo 3:** Criar a classe abstrata `BaseSlashCommand` e o registro central `CommandRegistry`.
4. **Passo 4:** Implementar comandos prioritários de memória e contexto (`/compact`, `/context`, `/cost`, `/timeline`, `/memory`).
5. **Passo 5:** Implementar comandos de alinhamento e operação (`/plan`, `/goal`, `/grill-me`, `/review`, `/diff`, `/doctor`, `/help`).
6. **Passo 6:** Escrever bateria de testes unitários validando despacho de argumentos e formatação de saídas.

---

## 8. Testes Automatizados & Critérios de Aceite (DoD)

### Cenários de Teste Obrigatórios
- **Teste 1:** Streaming de 500 tokens renderiza sem erros de formatação de tags Markdown incompletas.
- **Teste 2:** Diff de substituição cirúrgica gera painel visual com destaque em verde e vermelho.
- **Teste 3:** Todos os 20 comandos respondem adequadamente a argumentos válidos e exibem mensagem de uso para argumentos incorretos.

### Definition of Done (DoD)
- [ ] `StreamRenderer` e `DiffViewer` operando sem quebrar a rolagem do terminal.
- [ ] Catálogo oficial de Slash Commands implementado e testado.
- [ ] `pytest tests/unit/test_stream_renderer.py tests/unit/test_diff_viewer.py tests/unit/test_slash_commands.py` passando com 100% de sucesso.
- [ ] Cobertura de testes dos módulos $\ge 90\%$.
- [ ] Documentação de progresso atualizada em `.claudex/progress.md`.
