# Achados de TUI — Catálogo V-01 a V-17 (v0.5.1)

> **Origem:** análise visual e testes dinâmicos de 11/11/2026 no ORION v0.5.0-alpha (`tui-mcp`, `ptywright` e sonda pty+pyte com provider roteirizado, custo zero).
> **Regra desta versão:** a interface nova não pode herdar os bugs da antiga. Todo achado abaixo tem destino (sprint), critério de aceite e teste de regressão.
> **Confiança:** **C** = confirmado por captura ou medição · **I** = indício forte, exige confirmação no início da sprint · **H** = causa em hipótese (lida no código, não provada).
> Páginas de apoio (privadas): proposta Horizon e testes dinâmicos publicados como artifact `88m4yH8ZLNhXqVm9717Rkt`.

## Achados visuais (estáticos)

| ID | Conf. | Sintoma | Causa (arquivo) | Correção | Sprint |
|:---|:---:|:---|:---|:---|:---:|
| V-01 | C | "Dica" cortada em `Ctrl+C duplo p` a 110 colunas | Texto fixo sem variante por largura (`tui/status_bar.py`, `tui/banner.py`) | Três variantes por largura (>=100, 80 a 99, <80), sempre cabendo | 2 |
| V-02 | C | ~15 linhas em branco entre banner e prompt, que permanecem no histórico | `InteractivePrompt.dock_to_bottom()` (`tui/prompt.py:227`, chamado em `cli.py:92` e `cli.py:254`) preenche com linhas vazias | Remover o dock; prompt logo abaixo do conteúdo e sobe com ele | 2 |
| V-03 | C | Menu cinza chapado, setas ASCII `^ v`, ordem embaralhada, ícones `❯ › ●` sem critério | Estilo `completion-menu` sem estado selecionado forte, `ScrollbarMargin(display_arrows=True)`, ordem do completer (`tui/prompt.py:71-77,142-150`, `tui/completer.py`) | Token `sel`, rodapé de atalhos com posição, ordem por categoria, ícone só na linha selecionada | 2 |
| V-04 | C | Réguas do prompt claras e pesadas | `prompt.border` em `text_primary` (regra 3 de `CLI_AGENT_RULES.md`) | Novo token `rule` (`#566377`, 3,2:1 sobre o fundo) | 2 |
| V-05 | C | "your terminal doesn't support cursor position requests (CPR)" sobre o menu | Emulador sem CPR; o prompt_toolkit avisa na tela | Detectar e suprimir o aviso; documentar terminais suportados | 1 |
| V-06 | C | Rodapé de status presente num emulador e ausente em outro | `bottom_toolbar` do prompt_toolkit só aparece se o terminal responde CPR (confirmado na sonda: com CPR respondido, o rodapé volta) | O rodapé não pode depender de CPR (ADR-040) | 1 |
| V-07 | C | Instalação limpa mostra OFFLINE em vermelho, modelo `qwen2.5-coder:1.5b` e `AUTH: GitHub` vindo de fora de `~/.orion` | `settings.json` legado (K-04), `SessionStatusBar.from_environment()` | Estado neutro "sem provedor" com orientação de `/config`; AUTH só de `~/.orion` | 2 |
| V-08 | C | Figma e docs divergem (`Alt+T` vs `Alt+R`; mock sem réguas; PEP nível 2 vs 3) | Mock anterior às correções F-07/F-08 | Docs de design corrigidas nesta entrega; Figma Horizon vira a referência visual quando houver cota | 2 |

## Achados dinâmicos (só aparecem em movimento)

| ID | Conf. | Sintoma | Causa provável (arquivo) | Correção | Sprint |
|:---|:---:|:---|:---|:---|:---:|
| V-09 | C | Primeiro envio baixa 67 MB do HuggingFace (~16 s) no meio do turno; barras tqdm e aviso do HF Hub sujam a TUI e o rodapé | `fastembed.TextEmbedding(model_name=...)` carrega e baixa de forma preguiçosa (`memory/vector_store.py:114-116`) | Sem rede sem consentimento (ADR-040): só usa modelo em cache; sem cache cai no BM25 e oferece instalar; progresso pelo sink, nunca tqdm | 1 |
| V-10 | C | Bloco de código que abre durante o stream, em resposta mais alta que a tela, deixa um quadro de código vazio e duplicado no histórico | **H:** commit de bloco no scrollback ao abrir a cerca de código sem aguardar o fechamento (`tui/stream_renderer.py`, `_flush_text`/`OrionMarkdown`) | Só commitar bloco de código fechado; teste com cerca aberta e resposta maior que a tela | 1 |
| V-11 | C | Texto digitado durante o turno não ecoa por até ~10 s; Enter durante o turno enfileira e envia sozinho, sem indicador | O prompt só existe entre turnos (`cli.py:176`); o terminal enfileira as teclas sem eco | Spike: input leve durante o turno; plano B: indicador de fila (`1 na fila`) sem eco | 1 |
| V-12 | C | Tempo da ferramenta inclui a espera pela aprovação (`seq` instantâneo aparece com 8,4 s) | `StreamRenderer.start_tool` guarda `time.monotonic()` antes do PEP (`stream_renderer.py:253,272-280`) | Cronômetro começa na execução; a espera de aprovação é medida à parte | 1 |
| V-13 | C | Modal PEP fica no histórico sem registrar a decisão; prompt e rodapé somem durante o modal; nível exibido 3 contra 2 nos docs | `panels.py:314` mostra o nível real; `pause()` encerra o Live e leva o status junto | Linha de decisão (`✔ aprovado` ou `✖ negado`) sob o modal; status line permanece; docs corrigidas para o nível real | 1 e 2 |
| V-14 | C | Alt+E reimprime a saída inteira sem cabeçalho; Alt+Shift+E digita `E` e duplica o bloco do prompt | Bindings só para `("escape","e")` minúsculo (`tui/keybindings.py:105-106`) | Cabeçalho na expansão; alias para `E`; sem duplicar o prompt | 1 |
| V-15 | C | Esc duas vezes não fecha o menu, contra a especificação | `@kb.add("escape", filter=~has_completions)` (`keybindings.py:55`) deixa o Esc sem ação quando há menu | Esc com menu aberto chama `cancel_completion()` | 1 |
| V-16 | C | Ctrl+C com o menu aberto limpa o texto, mas o prompt sobe 8 linhas, deixando branco abaixo do rodapé; sem aviso de segundo Ctrl+C | Região do menu não é recuperada no redesenho | Redesenho sem resíduo; mensagem `Ctrl+C de novo para sair` por 2 s | 1 |
| V-17 | I | Cancelar com Ctrl+C descarta texto que já estava na tela (após ~60% da resposta, sobraram 3 linhas) | **H:** o Live é transiente (`stream_renderer.py:153`) e o caminho de cancelamento não chama `close()` para gravar a cauda (`session.py:1411`) | Confirmar com captura antes e depois; ao cancelar, gravar a cauda no histórico | 1 |

## Medições de referência (baseline, 110 colunas, ~2,3 mil caracteres a ~200 car/s)

| Métrica | Baseline | Meta da v0.5.1 |
|:---|:---|:---|
| Duração total do turno | 13,1 a 13,8 s | não piorar mais que 10% |
| Atualizações de tela | ~12 por segundo (153 em 13 s) | 10 a 12 por segundo, sem pausa maior que 300 ms após o primeiro token |
| Maior pausa no stream | 0,7 a 1,2 s (início do turno) | <= 1,2 s |
| CPU do ORION durante o stream | ~10% de um núcleo (medido no lab; os ~20% da sonda inicial estavam superestimados) | <= baseline × 1,2 (gate); sem otimização na Sprint 1 (1A.4) |
| Primeira mensagem da instalação | +16 s (download) | 0 s de rede; BM25 até haver modelo em cache |
| Pausa de 6 s no stream | tela muda 13 vezes, sem aviso de travamento | aviso discreto após 5 s sem token (`sem resposta há 5s`) |

## Não testado (entra como tarefa das sprints)

Modelo real do OpenRouter (`ORION_LIVE=1`, teto 15 das 50 req diárias), colar texto multilinha, `/model` e `/config` interativos, tema claro, reflow real do histórico num terminal gráfico (Ghostty, Kitty, GNOME Terminal) e fonte de glifos ausentes.

## Resolução da Sprint 1 (11/11/2026)

| ID | Estado | Nota |
|:---|:---|:---|
| V-05, V-06 | corrigido | Causa: filtro `renderer_height_is_known` da barra do `PromptSession`. Status line em janela própria; aviso de CPR removido |
| V-09 | corrigido | Só cache local; sem modelo, BM25 + aviso único; `/memory model install` com consentimento. Cache passa a `~/.orion/models/fastembed` (o padrão em `/tmp` some no reboot) |
| V-10 | corrigido | Duas causas: parte viva maior que a tela e corrida do Rich entre refresh e print. Janela de cauda + print sob o lock do Live |
| V-11 | corrigido (spike adotado) | `TypeAhead` em `cbreak`, eco na parte viva, fila e texto incompleto devolvido ao prompt |
| V-12 | corrigido | Tempo pausado pelo modal descontado |
| V-13 | corrigido | Decisão registrada; status line visível no modal; nível exibido é o real |
| V-14, V-15, V-16 | corrigido | Cabeçalho na expansão e aliases; Esc `eager` fecha o menu; prompt alinhado ao fundo e aviso de Ctrl+C |
| V-17 | **falso positivo** | Cenário passou no código antigo; mantido como regressão |
| V-01 a V-04, V-07, V-08 | Sprint 2 | Visual |
