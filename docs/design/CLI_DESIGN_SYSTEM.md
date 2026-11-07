# ORION — Especificação Mestra do CLI Design System & UX de Terminal

> **Status:** 🏛️ Documento Normativo Oficial (Congelado para Implementação)  
> **Versão de Referência:** v0.4.0+  
> **Benchmark de Mercado:** Claude Code (Anthropic), Google Antigravity CLI (`agy`), Hermes Agent (Nous Research)  
> **Referência Visual:** [Figma — O.R.I.O.N Stream CLI (v0.4.0)](https://www.figma.com/design/v4kP8u5X0plLLjjg7TAumJ). Em caso de divergência, este documento e `ORION_COLORS` prevalecem. No Figma, `✔` e `✖` são vetores porque a fonte de fallback ignora a cor do token; no terminal continuam sendo os glifos oficiais.  
> **Propósito:** Definir as regras visuais, arquitetura de componentes, wireframes de telas, catálogo de atalhos e padrões de renderização que **todo desenvolvedor e agente de IA** deve seguir rigorosamente ao criar ou alterar comandos, modais ou saídas da CLI do ORION.

---

## 1. Filosofia de Design & Padrão Anti-Emoji Monospace

### 1.1 Por que Emojis são Terminantemente Proibidos na CLI do ORION?

1. **Incompatibilidade Matemática de Células de Terminal (`wcwidth`):**
   - Emuladores de terminal baseiam-se em uma grade de caracteres de largura fixa (células monospace).
   - Emojis modernos utilizam sequências de múltiplos pontos de código Unicode combinados com *Zero-Width Joiners* (ZWJ) e seletores de variação (`U+FE0F`).
   - A biblioteca padrão do sistema operacional (`wcwidth` do C/Python) frequentemente calcula essas sequências como tendo largura `1` ou `0`, enquanto terminais modernos (Kitty, WezTerm, Ghostty, Alacritty, iTerm2, Windows Terminal) as desenham ocupando `2` células.
   - **Resultado do bug:** Quebra de colunas, desalinhamento de tabelas, texto "comido", e o cursor "flutuando" ou se deslocando incorretamente (*cursor drift*).
2. **Autoridade Estética de Engenharia:**
   - Ferramentas de alta precisão (Git, Docker, Kubernetes/kubectl, Claude Code, gh CLI) não utilizam emojis em suas interfaces operacionais.
   - O ORION adota **geometria monospace precisa**, utilizando glifos Unicode puros renderizados com elegância nas cores da paleta oficial.

### 1.2 Tabela Oficial de Glifos Monospace (Substituição de Emojis)

| Finalidade / Semântica | Proibido (Emoji) | Padrão Oficial ORION | Token de Estilo Rich | Exemplo de Aplicação |
| :--- | :--- | :--- | :--- | :--- |
| **Cursor do Prompt** | `>` / `👉` | `❯` | `accent_cyan bold` | `❯ digite sua instrução...` |
| **Comando Slash Ativo** | `📋` / `🎯` / `💡` | `❯` ou `●` | `accent_cyan` | `❯ /plan`, `● /goal` |
| **Item / Sub-item / Breadcrumb** | `📁` / `📄` | `›` | `text_dim` | `› src/orion/cli.py` |
| **Sucesso / Aprovado / Concluído** | `✅` | `✔` | `status_ok` (`#2EA043`) | `✔ Bash: npm test · 1.2s · exit 0` |
| **Falha / Erro / Negado** | `❌` / `🚫` | `✖` | `diff_del` (`#F85149`) | `✖ Falha na compilação` |
| **Aviso / Atenção / Alerta** | `⚠️` | `!` ou `▲` | `pep_warn` (`#D29922`) | `▲ PEP: Confirmação necessária` |
| **Segurança / Nuclear / PEP** | `🔐` / `🔒` / `☢️` | `[PEP]` ou `■` | `pep_warn` / `accent_cyan` | `[PEP NÍVEL 2] Mutação em arquivo` |
| **Memória Cognitiva** | `🧠` | `● [Memory]` | `accent_blue` | `● [Memory] Fato confirmado` |
| **Spinner / Processamento** | Caracteres aleatórios | Braille Spinner `⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏` | `accent_cyan` | `⠋ Pensando [high effort]...` |
| **Status Online** | `🟢` | `●` | `status_ok` (`#2EA043`) | `Ready ●` |
| **Status Offline** | `🔴` | `●` | `status_offline` (`#DA3633`) | `Offline ●` |
| **Separador Discreto** | `|` / `-` | `·` ou `│` | `text_dim` / `border_subtle` | `3.4k tokens · $0.012` |
| **Bordas Arredondadas** | Cantos retos feios | `╭`, `╮`, `╰`, `╯`, `─`, `│` | `border_subtle` (`#262F3D`) | Caixas e painéis de diff |

---

## 2. Paleta Oficial & Ergonomia Visual ("Deep Cosmos & Glacial Platinum")

A paleta oficial foi calibrada para uso contínuo de **12 horas ou mais**, eliminando o contraste excessivo do branco puro (`#FFFFFF`) e o efeito flashbang do preto absoluto (`#000000`).

| Token Semântico | Código Hexadecimal | Finalidade no Terminal | Relação de Contraste WCAG |
| :--- | :--- | :--- | :--- |
| **`bg_canvas`** | `#0B0E14` | Fundo oficial do terminal / base | — |
| **`surface_panel`** | `#151B23` | Fundo de painéis e cards flutuantes | — |
| **`border_subtle`** | `#262F3D` | Bordas de caixas, linhas divisórias e réguas | — |
| **`text_primary`** | `#E6EDF3` | Texto principal de respostas do agente e corpo de Markdown | 13.5:1 (AAA) |
| **`text_user`** | `#F0F6FC` | Texto digitado pelo desenvolvedor no prompt | 14.8:1 (AAA) |
| **`text_dim`** | `#8B949E` | Metadados, números de linha, timestamps e separadores | 6.2:1 (AA) |
| **`accent_cyan`** | `#00D2FF` | Identidade visual ORION, cursor `❯`, status ativo | Destaque primário |
| **`accent_blue`** | `#3A7BD5` | Raciocínio (thinking), categorias e links | Destaque secundário |
| **`diff_add`** | `#3FB950` | Diffs de adição (`+`) | Sinalização verde |
| **`diff_del`** | `#F85149` | Erro (`✖`), diffs de remoção (`-`) | Sinalização vermelha |
| **`diff_add_tint`** | `#12261C` | Fundo de linha adicionada (`diff_add` a 14% sobre `bg_canvas`) | Só dentro do painel de diff |
| **`diff_del_tint`** | `#2C171B` | Fundo de linha removida (`diff_del` a 14% sobre `bg_canvas`) | Só dentro do painel de diff |
| **`status_ok`** | `#2EA043` | Sucesso (`✔`), status online | Sinalização verde |
| **`status_offline`** | `#DA3633` | Modo offline / failover | Sinalização vermelha |
| **`pep_warn`** | `#D29922` | Governança PEP, avisos (`!`), autorizações pendentes | Sinalização âmbar |

> [!IMPORTANT]
> **Regra de Ouro do Fundo:** O terminal NUNCA deve desenhar faixas de fundo sólidas ocupando 100% da largura da tela (ex: preencher toda a largura com `bg:surface_panel`). O fundo nativo do terminal (`default` / `bg_canvas`) deve prevalecer, deixando o terminal leve e respirável.

---

## 3. Arquitetura da Superfície Base (Living Stream)

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. SPLASH BANNER ADAPTATIVO (80 / 120 / 200 colunas)                       │
├─────────────────────────────────────────────────────────────────────────────┤
│ 2. FLUXO CONTÍNUO DE CHAT & EXECUÇÃO (Rolagem Nativa do Terminal)           │
│    • Bloco de Pensamento (Thinking... colapsável)                           │
│    • Cards de Ferramentas (⠋ Running -> ✔ Completed)                         │
│    • Streaming Markdown com Syntax Highlighting                             │
│    • Diffs Cirúrgicos formatados (+ / -)                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│ 3. DYNAMIC INPUT PROMPT (Claude Code / gh style)                            │
│    ❯ digite sua instrução... (expansão vertical suave em multilinhas)       │
├─────────────────────────────────────────────────────────────────────────────┤
│ 4. CLEAN STATUS LINE (Fundo transparente, separadores · sutis)             │
│    claude-3-7-sonnet · 3.4k tokens ($0.0120) · thinking: high · Ready ●    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 O Dynamic Minimalist Input Prompt
* **Cursor Principal:** `❯ ` formatado em `accent_cyan bold`.
* **Comportamento Monolinha (Padrão):** Ocupa estritamente 1 linha na base da tela.
* **Comportamento Multilinha:** Ao colar blocos de código ou usar `Alt+Enter` / `Shift+Enter`, a área de entrada expande verticalmente conforme a quantidade de linhas do texto. Ao deletar ou limpar, **retrai imediatamente para 1 linha**, sem deixar qualquer resíduo ou linha horizontal fantasma.
* **Zero Túneis Rígidos:** Fica estritamente proibida a injeção de janelas `char="─"` estáticas no container do `prompt_toolkit`. A área de input deve fluir naturalmente no terminal.

### 3.2 A Linha de Status Inferior (Clean Bottom Line)
* **Fundo:** Transparente / herda o fundo padrão do terminal (`bg:default`).
* **Estrutura:**
  ```text
    accept-edits · claude-3-7-sonnet · 12.4k in / 3.4k out · $0.0882 / R$ 0,507 · thinking: high · PEP: 2 · Ready ●
  ```
* **Estado:** `Ready ●` em repouso, `Working ●` durante um turno e `Offline ●` sem gateway de nuvem. Durante o turno, a mesma linha é desenhada pelo `StreamRenderer` abaixo do spinner.
* **Modo:** o modo operacional (§5.1) abre a linha em `accent_blue`.
* **Adaptação Responsiva por Largura:**
  - **$\ge 110$ colunas:** Exibe modo, modelo, tokens acumulados (in/out), custo em USD/BRL, esforço de raciocínio, nível PEP e status dot.
  - **80 a 109 colunas:** Abrevia modelo, resume tokens (`3.4k tok`), exibe custo em USD e status dot.
  - **$< 80$ colunas:** Exibe modelo abreviado, custo em USD e status dot.

### 3.3 Streaming de Respostas da IA
* **Formatação:** Markdown contínuo renderizado via `Rich.Live` com realce sintático.
* **Layout:** Parágrafos fluem sem caixas ou contornos desnecessários ao redor de cada frase. Código é encapsulado em blocos com realce de sintaxe e bordas finas arredondadas.
* **Rolagem:** Sempre em `stdout` contínuo. O desenvolvedor rola com o trackpad ou mouse sem bloqueio de tela cheia.

### 3.4 Bloco de Raciocínio (Chain of Thought / Thinking)
* **Durante a Inferência:** Exibe um indicador atenuado com spinner:
  ```text
  ⠋ Pensando [high effort]... (3.2s)
  ```
* **Após Concluir o Pensamento:** O bloco é colapsado automaticamente para:
  ```text
  ▼ Raciocínio formulado em 4.1s (pressione Alt+R para expandir)
  ```
* **Quando Expandido:** Apresenta o raciocínio em cinza atenuado (`#8B949E`) com uma guia vertical sutil à esquerda (`│ `):
  ```text
  │ O desenvolvedor deseja reorganizar a arquitetura do prompt engine.
  │ Analisando o container do prompt_toolkit e removendo a injeção estática...
  ```

### 3.5 Cards de Execução de Ferramentas (Tool Calls)
* **Em Execução:**
  ```text
  ⠋ Bash: pytest tests/unit/test_cli.py
  ```
* **Concluído com Sucesso:**
  ```text
  ✔ Bash: pytest tests/unit/test_cli.py · 0.8s · exit 0
  ```
* **Concluído com Erro:**
  ```text
  ✖ Bash: cargo build · 2.4s · exit 1
  ```
* **Tratamento de Saída (Stdout/Stderr da Ferramenta):**
  - **Até 5 linhas:** Exibidas diretamente identadas com barra sutil à esquerda (`│ `).
  - **Mais de 5 linhas:** Exibe as 3 primeiras linhas, uma linha de colapso atenuada:
    ```text
    │ [+42 linhas ocultas · pressione Alt+E para expandir]
    ```
    e as 2 últimas linhas.

---

## 4. Blueprints das Sub-telas e Telas Modais

Qualquer comando que renderize uma interface interativa ou modal **deve seguir obrigatoriamente** estes padrões estruturais:

### 4.1 Blueprint A: O Painel de Configurações Interativo (`/config`)

```text
╭─ O.R.I.O.N — Painel de Configurações Operacionais ─────────────────────────────╮
│                                                                                │
│  Categorias (↑/↓)         Configuração: Modelo & Provedores                    │
│  ─────────────────        ─────────────────────────────────────────────        │
│  ● Modelo & IA            Provedor Primário:   [ OpenRouter ]                  │
│    Raciocínio & Thinking  Modelo Ativo:        [ claude-3-7-sonnet-thinking ]  │
│    Governança PEP         Modo de Roteamento:  [ auto (dinâmico) ]             │
│    Memória & Esferas      Fallback Offline:    [ Ollama (qwen2.5-coder) ]      │
│    Custos & Orçamento                                                          │
│    Identidade & Voz       Parâmetros Operacionais:                             │
│                           • Janela de Contexto: 200,000 tokens                 │
│                           • Custo por 1M Tok:   $3.00 in / $15.00 out          │
│                                                                                │
├────────────────────────────────────────────────────────────────────────────────┤
│  [↑/↓] Navegar  │  [Tab] Alternar Painel  │  [Enter] Alterar  │  [Esc/q] Sair  │
╰────────────────────────────────────────────────────────────────────────────────╯
```

* **Navegação:**
  - `↑` / `↓`: Navega entre itens da lista ativa.
  - `Tab` / `Shift+Tab`: Alterna foco entre coluna da esquerda (Categorias) e coluna da direita (Opções).
  - `Enter` / `Espaço`: Seleciona valor, abre lista de opções ou altera checkbox.
  - `Esc` ou `q`: Grava alterações em `~/.orion/config.json` e retorna ao chat principal.

### 4.2 Blueprint B: Seletor de Modelos de IA (`/model`)

```text
╭─ Seleção de Modelo de IA ──────────────────────────────────────────────────────╮
│  Provedor     Modelo                          Contexto    Custo (In/Out 1M)    │
│  ────────────────────────────────────────────────────────────────────────────  │
│  ● OpenRouter  claude-3-7-sonnet-thinking      200k        $3.00 / $15.00       │
│    OpenRouter  claude-3-5-haiku                200k        $0.80 / $4.00        │
│    OpenRouter  gemini-2.5-pro                  1000k       $1.25 / $5.00        │
│    OpenRouter  deepseek-r1                     64k         $0.55 / $2.19        │
│    Ollama      qwen2.5-coder:7b (Local)        32k         $0.00 (Offline)      │
╰────────────────────────────────────────────────────────────────────────────────╯
   Digite para filtrar | [Enter] Confirmar | [Esc] Cancelar
```

### 4.3 Blueprint C: Inspetor de Memória e Timeline (`/memory`, `/timeline`)

```text
╭─ O.R.I.O.N — Inspetor das 5 Esferas Cognitivas ────────────────────────────────╮
│  Esfera                Status     Itens       Armazenamento                    │
│  ────────────────────────────────────────────────────────────────────────────  │
│  ● user_profile        Ativa      Daniel Dev  ~/.orion/profile.json            │
│  ● system_identity     Ativa      Jarvis      Imutável + persona.json          │
│  ● system_environment  Ativa      Saudável    Headroom Guard (> 1.5GB)         │
│  ● project_decisions   Ativa      18 Fatos    CONFIRMED (14) / INFERRED (4)    │
│  ● timeline_episodic   Ativa      842 Eventos ~/.orion/timeline.db (WAL)       │
╰────────────────────────────────────────────────────────────────────────────────╯
   [F] Ver Fatos Confirmados │ [T] Linha do Tempo de Hoje │ [Esc] Fechar
```

### 4.4 Blueprint D: Diálogo de Governança PEP / Confirmação HITL

Quando o agente tentar executar ações de **Nível PEP 2** (mutações de arquivos ou comandos bash) ou **Nível PEP 3** (ações de alto risco), a CLI exibe a caixa formal de autorização:

```text
╭─ [PEP NÍVEL 2] Autorização Operacional Requerida ──────────────────────────────╮
│  Ação Solicitada: Execução de Comando no Sistema Operacional                   │
│  Comando:        git push origin main                                          │
│  Impacto:        Atualiza o repositório remoto com os commits locais           │
╰────────────────────────────────────────────────────────────────────────────────╯
   [y] Aprovar   [n] Rejeitar   [e] Editar Comando   [a] Sempre Permitir na Sessão
```

### 4.5 Blueprint E: Composição de Contexto (`/context`)

```text
╭─ Janela de Contexto  48.2k / 200k (24%) ───────────────────────────────────────╮
│  ███▒▒▓▓▓▓███████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │
│  █ sistema         6.2k    3.1%                                                │
│  █ conversa       15.2k    7.6%                                                │
│  ░ livre         151.8k   75.9%                                                │
╰────────────────────────────────────────────────────────────────────────────────╯
```

### 4.6 Blueprint F: Livro-Razão da Sessão (`/cost`)

```text
╭─ Livro-Razão da Sessão ────────────────────────────────────────────────────────╮
│  Tipo                  Tokens         USD                                      │
│  Entrada               12,400     $0.0372                                      │
│  Saída                  3,400     $0.0510                                      │
│  Cache                      0     $0.0000                                      │
│  Total                 15,800     $0.0882   R$ 0,507                           │
╰────────────────────────────────────────────────────────────────────────────────╯
```

---

## 5. Catálogo de Comandos da CLI & Atalhos de Teclado

### 5.1 Modos Operacionais do Agente (Padrão Claude Code / Antigravity)

O agente possui 4 modos de operação comutáveis instantaneamente:

| Modo Operacional | Descrição de Comportamento | Nível PEP Associado | Regra de Gate no PEP |
| :--- | :--- | :--- | :--- |
| **`plan`** | Modo de planejamento estrito: pesquisa o repositório, lê arquivos, formula artefatos de plano e colhe aprovação. Nenhuma mutação de código ou comando de escrita é executado. | PEP Nível 1 (Read-Only) | `SUPERVISED` com negação automática de todo Nível 2+ |
| **`accept-edits`** | Modo de codificação assistida: aceita e aplica edições e correções de código no workspace automaticamente. Pede autorização apenas para comandos de shell (`bash`) ou ações externas. | PEP Nível 2 (Mutação de Código) | `WORKSPACE_AUTO`: edições passam, `run_command` pede autorização |
| **`auto`** | Modo autônomo prolongado (`/goal`): executa tarefas complexas com auto-recuperação (*Self-Healing*), aplicando edições e rodando testes sem interromper o fluxo para cada passo trivial. | PEP Nível 2 Supervisionado | `FULLY_AUTO`: invariantes (sudo, escopo, nuclear) continuam valendo |
| **`manual`** | Modo estritamente supervisionado: exige autorização do usuário (`[y/n]`) antes de cada edição de arquivo ou execução de comando. | PEP Nível 3 (HITL Rigoroso) | `SUPERVISED`: toda mutação pede autorização |

### 5.2 Matriz Completa de Atalhos de Teclado

| Combinação de Teclas | Ação Executada | Referência de Indústria |
| :--- | :--- | :--- |
| **`Shift + Tab`** (ou `Shift + Alt`) | Alterna ciclicamente o modo do agente: `plan` $\rightarrow$ `accept-edits` $\rightarrow$ `auto` $\rightarrow$ `manual` | Claude Code & Antigravity |
| **`Alt + T`** | Alterna o nível de esforço de raciocínio: `HIGH` $\rightarrow$ `MEDIUM` $\rightarrow$ `LOW` $\rightarrow$ `OFF` | Claude Code (`Opt+T`) |
| **`Alt + O`** | Ativa / desativa o modo ultra-rápido (*Fast Mode*) | Claude Code (`Opt+O`) |
| **`Alt + R`** | Expande o último bloco de raciocínio no fluxo | ORION |
| **`Alt + E`** | Expande a última saída de ferramenta colapsada | ORION |
| **`Alt + Enter`** ou `Shift + Enter` | Insere quebra de linha no prompt sem submeter (entrada multilinha) | Terminal Padrão / Claude Code |
| **`Ctrl + C` (1 toque)** | Cancela a inferência/streaming ou ferramenta em execução, mantendo o processo e memórias abertos | Claude Code & Hermes Agent |
| **`Ctrl + C` (2 toques)** | Encerra o processo da CLI com segurança | Padrão Linux / Claude Code |
| **`Ctrl + L`** | Limpa e redesenha a tela de forma atômica sem perder o histórico do chat | Bash / Zsh / Claude Code |
| **`Esc`** | Cancela menu de autocompletar, fecha telas modais (`/config`) ou limpa texto digitado | Vim / IDEs Modernas |
| **`Tab`** | Dispara ou seleciona o autocompletar flutuante de Slash Commands (`/`) ou arquivos (`@`) | Linux Standard |

### 5.3 O Catálogo Oficial dos 23 Slash Commands (`/`)

| Categoria | Comando | Descrição Operacional |
| :--- | :--- | :--- |
| **Cognitivo & Raciocínio** | `❯ /plan <meta>` | Ativa o modo de planejamento estrito: pesquisa, gera artefato e colhe aprovação. |
| | `❯ /goal <meta>` | Execução autônoma prolongada com auto-recuperação (*Self-Healing*). |
| | `❯ /grill-me` | Entrevista socrática investigativa para esclarecer requisitos antes do código. |
| | `❯ /review` | Análise crítica de código, arquitetura e segurança nos diffs recentes. |
| **Memória & Habilidades** | `❯ /learn` | Auto-destilação: converte a solução da sessão em uma skill `SKILL.md` reutilizável. |
| | `❯ /memory` | Inspeciona as 5 Esferas Cognitivas e o registro de fatos confirmados. |
| | `❯ /timeline` | Exibe a linha do tempo contínua da sessão e histórico de eventos. |
| | `❯ /recall <termo>` | Busca híbrida RRF no grafo de memória para resgatar decisões ou bugs passados. |
| **Contexto & Ramificações** | `❯ /compact [foco]` | Compactação inteligente da janela de tokens preservando cauda vital e arquivos. |
| | `❯ /context` | Gráfico de composição de tokens da janela de contexto ativa. |
| | `❯ /branch <nome>` | Ramificação de contexto isolada para investigações e experimentos sem poluição. |
| | `❯ /merge` | Síntese de checkpoint de 3 a 5 linhas comitada na Main Timeline. |
| **Operação & Governança** | `❯ /diff` | Painel syntax-highlighted de todas as modificações da sessão. |
| | `❯ /undo` | Rollback atômico da última mutação de código via git checkpoint. |
| | `❯ /run <cmd>` | Execução cirúrgica de comando no SO sob o crivo do PEP. |
| | `❯ /doctor` | Diagnóstico de saúde do ambiente (Python, hardware, Ollama, chaves de API). |
| | `❯ /cost` | Livro-razão financeiro com tokens de entrada, saída, cache e total em USD e BRL. |
| | `❯ /model` | Seletor interativo de modelos com filtro por digitação. |
| | `❯ /config` | Painel interativo para alternar provedores, modelos, personas e governança PEP. |
| | `❯ /mcp` | Gerencia conexões e ferramentas do Model Context Protocol (stdio / SSE). |
| | `❯ /voice` | Controla o daemon de presença ambiente e voz headless. |
| | `❯ /clear` | Limpa a tela do terminal preservando o contexto e memórias. |
| | `❯ /help` | Guia completo de comandos e catálogo de atalhos de teclado. |

---

## 6. Governança de Evolução do Design

Qualquer alteração na interface da CLI deve respeitar o princípio **Doc-First**:
1. Nenhuma cor fora de [`ORION_COLORS`](file:///home/danieldev/orion-agent/src/orion/tui/theme.py) pode ser introduzida sem atualização prévia deste documento.
2. Nenhum emoji decorativo pode ser adicionado em novos comandos ou mensagens de sistema.
3. Toda nova tela modal deve implementar navegação via teclado (`↑/↓`, `Tab`, `Enter`, `Esc/q`) e layout delimitado por bordas arredondadas finas.
