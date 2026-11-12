# Sprint — v0.5.1 Sprint 2: Horizon Visual

> **Status:** 📋 Planejando (aguarda conclusão da Sprint 1 e comando de início do Senhor)  
> **Versão Relacionada:** v0.5.1  
> **Responsável / Agente:** Daniel Dev & Claude (via ORION)  
> **Data de Início:** —  
> **Data de Conclusão:** —  
> **ADRs:** 039, 040 · **Achados:** V-01 a V-04, V-07, V-08 · **Referência:** `docs/design/horizon/`

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Aplicar a identidade Horizon aprovada em 11/11/2026 sobre a base estabilizada da Sprint 1, mantendo a paleta Deep Cosmos e o bloco Stellar.
* **Dependências Prévias:** Sprint 1 concluída (harness e bugs de comportamento corrigidos).
* **Entregável Verificável:** os cenários `test_layout_widths` e o golden das cinco telas de `docs/design/horizon/` passam em 110, 80 e 60 colunas; captura `tui-mcp` das telas reais confere com a referência.

---

## 2. Contexto de Engenharia

* **Por que existe:** banner de 16 linhas com seis badges, vão vazio até o prompt, menu cinza sem seleção, réguas pesadas, PEP sem hierarquia, "Dica" cortada. Detalhes em `../achados-tui.md`.
* **Referências de mercado:** Claude Code (hierarquia por peso e cor, não por caixas; degradação para ANSI), Hermes (tokens em arquivo, cronômetro por resposta). Pesquisa e limites no artifact `88m4yH8ZLNhXqVm9717Rkt`.
* **Decisões:** ADR-039 (identidade) e ADR-040 (sem CPR, sem rede).

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Antes | Depois |
| :--- | :--- | :--- |
| **Banner** | Logo, 2 linhas de título, 3 linhas de badges em 2 colunas, 2 réguas, dica | Logo à esquerda, informação à direita (9 linhas no total), uma dica que cabe |
| **Posição do prompt** | Encostado no rodapé, com ~15 linhas vazias acima | Logo abaixo do conteúdo; sobe com ele |
| **Réguas** | `text_primary` | `rule` `#566377` |
| **Menu** | Bloco cinza, `^ v`, ícones variados | Seleção com `sel`, `❯` só na linha ativa, categoria à direita, rodapé `↑↓ navegar · Tab aceitar · Esc fechar · n/N` |
| **Ferramenta** | `✔ Read: caminho · 0.1s` | `✔ Read  caminho  ·  0,1s` com linha `› 212 linhas` |
| **Diff** | Moldura `border_subtle`, `-` | Moldura `rule`, título com `+a −b`, `−` tipográfico |
| **PEP** | Moldura `border_subtle` | Moldura `pep_warn`, teclas coloridas por efeito, `Esc cancela` |
| **Status line** | `accept-edits · modelo · tokens · custo · thinking · PEP · Ready` | `modo · modelo · 24% ctx · $ · PEP n · estado ●`; estados `Ready`, `Working`, `Aguardando`, `Offline` |
| **Cor** | Só truecolor | Mapeia para 256 cores; respeita `NO_COLOR` |

---

## 4. Escopo da Sprint

### ✅ No Escopo
- [ ] **2.1 — Tokens (`theme.py`):** `rule #566377`, `faint #7D8590`, `sel #1B2634`; aliases Rich; `test_theme.py` valida contraste mínimo (rule >= 3:1, faint >= 4.5:1 sobre `bg_canvas`) e que nenhuma cor fica fora de `ORION_COLORS`.
- [ ] **2.2 — Banner (`banner.py`, `status_bar.py`):** layout lateral >= 100 colunas; abaixo disso, texto sob o logo; abaixo de 70, logo reduzido de 4 linhas já existente. Gradiente vertical cyan para azul Órion por linha. Dica em três variantes (V-01). Versão vem de `__version__`.
- [ ] **2.3 — Estado inicial neutro (V-07):** sem provedor configurado mostra `● sem provedor · /config` em `pep_warn`, nunca vermelho de erro; `AUTH` só se vier de `~/.orion`.
- [ ] **2.4 — Prompt (`prompt.py`, `cli.py`):** remover `dock_to_bottom` e suas chamadas (`cli.py:92` e `cli.py:254`); réguas em `rule`; placeholder `digite sua instrução…` em `faint`; `/clear` e redimensionamento sem sobras.
- [ ] **2.5 — Menu (`prompt.py`, `completer.py`):** estilos `completion-menu.*` com `surface_panel` e `sel`; linha ativa com `❯` e nome em `accent_cyan` negrito; categoria à direita em `faint`; ordem estável por categoria e prefixo antes de fuzzy; sem setas ASCII de rolagem (posição `n/N` no rodapé); altura máxima 8.
- [ ] **2.6 — Ferramentas (`stream_renderer.py`):** nome em negrito, argumento em `text_dim`, tempo em `faint` com vírgula decimal; linha de resultado `  › ` por tool: `read_file` linhas, `edit_file` e `write_file` `+a −b`, `run_command` código de saída e linhas, `grep`/`glob` contagem, `web_fetch` status e tamanho. Resultado ausente não gera linha.
- [ ] **2.7 — Diff (`diff_viewer.py`):** moldura `rule`; título `arquivo  +a −b` com cores semânticas; números de linha em `faint`; sinal `−` (U+2212).
- [ ] **2.8 — PEP (`panels.py`):** moldura e título em `pep_warn`; rótulos em `text_dim`, comando em `accent_cyan`; teclas `y` verde, `n` vermelho, demais em `text_primary`; linha de decisão (da Sprint 1) com `✔`/`✖`.
- [ ] **2.9 — Status line (`status_bar.py`):** novo conjunto de segmentos e abreviações por largura (>=110, 80 a 109, <80); `% ctx` vem do cálculo do `/context`; estados e cores conforme §7 de `CLI_DESIGN_SYSTEM.md`.
- [ ] **2.10 — Cor (`console.py` ou `theme.py`):** detectar profundidade de cor; sem truecolor, mapear tokens para a paleta de 256 cores mais próxima; `NO_COLOR` remove cor mantendo negrito.
- [ ] **2.11 — Documentação (V-08):** `CLI_DESIGN_SYSTEM.md`, `CLI_AGENT_RULES.md` e `ASCII_ART_IDENTITY.md` alinhados (a base foi feita na entrega da spec); golden das cinco telas; arquivo `.claudex/system_patterns.md` com os invariantes visuais.
- [ ] **2.12 — Figma (opcional):** quando houver cota do MCP, criar a página "Proposta Horizon" a partir da grade de `docs/design/horizon/` e atualizar o link no `CLI_DESIGN_SYSTEM.md`.

### 🚫 Fora de Escopo
- Tema claro, skins por arquivo, animação de boot, imagens (Kitty/Sixel), eDEX.
- Novos slash commands. Se algum surgir, segue `CLI_AGENT_RULES.md` §2.
- Mudar comportamento do núcleo (tudo que era comportamento ficou na Sprint 1).

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/tui/{theme,banner,status_bar,prompt,completer,stream_renderer,diff_viewer,panels,console}.py [mod]
src/orion/cli.py                                   [mod] sem dock_to_bottom
tests/unit/{test_theme,test_banner,test_status_bar,test_completer,test_diff_viewer,test_panels}.py [mod]
tests/lab/scenarios/test_layout_widths.py          [novo]
tests/lab/golden/{splash-110,splash-80,autocomplete-110,stream-110,pep-110}.txt [novo, de docs/design/horizon]
docs/design/{CLI_DESIGN_SYSTEM,CLI_AGENT_RULES,ASCII_ART_IDENTITY}.md [mod]
.claudex/system_patterns.md                        [mod]
```

---

## 6. Contratos de Código & Tipagem

```python
# theme.py — tokens novos (valores em CLI_DESIGN_SYSTEM.md §7)
ORION_COLORS |= {"rule": "#566377", "faint": "#7D8590", "sel": "#1B2634"}

def tool_result_line(tool: str, result: ToolResult) -> str | None:
    """Resumo de uma linha para `  › ...`; None quando não há o que resumir."""

def status_segments(width: int, state: Literal["Ready", "Working", "Aguardando", "Offline"]) -> list[tuple[str, str]]: ...

def color_depth(env: Mapping[str, str], is_tty: bool) -> Literal["truecolor", "256", "none"]: ...
```

---

## 7. Estratégia de Implementação

1. 2.1 e 2.10 primeiro (base de cor e fallback), depois o que é visível da esquerda para a direita: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9.
2. Cada item: teste unitário + cenário do lab + captura `tui-mcp` comparada com `docs/design/horizon/`. Ciclo de `.claudex/tooling.md` §3 (capturar, comparar, mapear, corrigir, recapturar).
3. 2.11 ao final, congelando o golden. 2.12 se houver cota.
4. Validação manual do Senhor em Ghostty/Kitty/GNOME Terminal (reflow e fonte).
5. Commit único: `feat(tui): v0.5.1 Sprint 2 — identidade Horizon`.

---

## 8. Testes & Critérios de Aceite (DoD)

- CA-07, CA-09, CA-10 e CA-11 da `VERSION.md` verdes; golden das cinco telas igual à referência (estrutura e texto; cores verificadas por `snapshot_ansi`).
- `grep -r -E '[\U00010000-\U0010ffff]' src/` sem emoji novo; todas as cores em `ORION_COLORS`; `−` só no diff.
- Réguas: sem linha fantasma com menu aberto, multilinha, `Alt+Enter`, envio e cancelamento (cenários F-07/F-08 mantidos).
- Cobertura >= 85%; `ruff` e `mypy` limpos.
- [ ] Rodada com o OpenRouter free (<= 15 req) com capturas dos três tipos de turno (CA-12).
- [ ] `.claudex/progress.md`, `active_context.md` e a tabela da `VERSION.md` atualizados.

## 8.1 Registro de implementação

_(preencher ao concluir.)_

---

## 9. Critérios de Parada

1. Cor fora de `ORION_COLORS`, emoji ou fundo sólido na largura total da status line.
2. Regressão das réguas aprovadas (F-07/F-08).
3. Texto que ultrapassa a largura em 110, 80 ou 60 colunas.
4. Mudança de comportamento do núcleo dentro desta sprint (volta para a Sprint 1).
5. Queda de cadência ou aumento de CPU em relação ao baseline da Sprint 1.
