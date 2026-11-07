# ORION — Regras Mandatórias de Interface para Agentes de IA (CLI Agent Rules)

> **Público-Alvo:** Antigravity, Claude, Gemini, ORION Core ReAct e qualquer agente autônomo que receba tarefas para modificar, criar ou estender a CLI do ORION.  
> **Referência Obrigatória:** [`docs/design/CLI_DESIGN_SYSTEM.md`](CLI_DESIGN_SYSTEM.md)

---

## 1. As Regras de Ouro Invioláveis (O que NUNCA Fazer)

1. **NUNCA UTILIZE EMOJIS EM NENHUM COMPONENTE DA CLI:**
   * É estritamente proibido adicionar emojis (`📋`, `🎯`, `🧠`, `⚠️`, `✅`, `❌`, `📁`, `⚙️`, etc.) em nomes de comandos, ícones de autocompletar, títulos de tabelas, mensagens de log, status bars ou modais.
   * **Por quê:** Emojis quebram o cálculo de largura de caracteres (`wcwidth`), causam *cursor drift*, quebram colunas em emuladores como Kitty, Alacritty, Ghostty e iTerm2, e rebaixam a percepção de seriedade e autoridade do agente.
   * **O que usar:** Use exclusivamente a **Tabela de Glifos Monospace** aprovada: `❯`, `●`, `✔`, `✖`, `!`, `[PEP]`, `›`, `·`, `│`.

2. **NUNCA PINTE FUNDO SÓLIDO NA LARGURA TOTAL DA LINHA DE STATUS INFERIOR:**
   * É estritamente proibido aplicar `bg:{surface_panel}` ou qualquer outra cor de fundo em 100% da largura da barra inferior ou em espaçadores vazios (`" " * space_between`).
   * **Por quê:** Cria uma faixa retangular pesada e feia que nenhum agente moderno (Claude Code, Antigravity) possui.
   * **O que fazer:** A linha de status deve repousar sobre o fundo nativo do terminal (`default`), com textos atenuados e separadores discretos (`·` ou `│`).

3. **RÉGUAS DO PROMPT: SOMENTE AS DUAS APROVADAS, DENTRO DO `HSplit` (F-07/F-08):**
   * O container do prompt tem exatamente **duas** réguas `Window(char="─", height=1)` em `text_primary` (clara; `border_subtle` é escura demais e some no fundo do terminal), uma acima e outra abaixo do input (estilo Claude Code), inseridas em `InteractivePrompt.__init__`. Por serem filhas do `HSplit`, acompanham a altura do input (quebra de linha e `Alt+Enter`) e permanecem no scrollback após o envio.
   * A janela de input tem `dont_extend_height`: sem isso, com o prompt no rodapé, sobram linhas vazias entre o texto e a régua de baixo ao apagar linhas. As réguas devem seguir sempre o texto digitado.
   * É proibido adicionar outras janelas horizontais estáticas ou caixas laterais ao redor do texto.
   * **Por quê:** janelas adicionais geraram "linhas fantasmas" com o menu de autocompletar e entradas multilinhas. A configuração aprovada foi validada em pty (vazio, quebra, `Alt+Enter`, menu aberto/fechado, envio).
   * O texto digitado fica em negrito na cor nativa do terminal (nunca fixar cor clara: some em fundo claro).

4. **NUNCA DESPEJE RESPOSTAS LONGAS OU RACIOCÍNIO BRUTO SEM COLAPSO:**
   * O raciocínio do modelo (Thinking) deve ser colapsado para 1 linha (`▼ Raciocínio formulado em Xs`) após a conclusão, permitindo expansão opcional.
   * Saídas de ferramentas (`run_command`) acima de 5 linhas devem exibir apenas as primeiras 3 e últimas 2 linhas com indicador de colapso `[+X linhas ocultas · Alt+E para expandir]`.

5. **NUNCA LIMPE A TELA COM COMANDOS BRUTOS DO SO:**
   * Nunca utilize `os.system("clear")` ou `os.system("cls")`. Apenas `console.clear()` do Rich ou sequência ANSI atômica sem perda de histórico.

---

## 2. Como Adicionar um Novo Slash Command (`/`)

Ao receber uma instrução como *"Adicione o comando /xyz que faz tal coisa"*:

1. **NÃO crie uma lógica ad-hoc solta dentro de `cli.py`**.
2. **Defina os Metadados em [`src/orion/tui/completer.py`](file:///home/danieldev/orion-agent/src/orion/tui/completer.py):**
   ```python
   # Exemplo correto (ZERO emojis):
   SlashCommandInfo(
       "/xyz",
       "Descrição concisa do comando",
       icon="❯",           # Use "❯" ou "●", NUNCA emoji
       category="operation",
   )
   ```
3. **Crie a Classe do Comando no módulo da sua categoria em `src/orion/tui/commands/` (`cognitive.py`, `memory.py`, `context.py` ou `operation.py`) herdando de `BaseSlashCommand`:**
   ```python
   class XyzCommand(BaseSlashCommand):
       name = "/xyz"
       description = "Descrição concisa"
       
       async def execute(self, args: str, context: CommandContext) -> CommandResult:
           # Lógica do comando respeitando a paleta oficial de cores
           return CommandResult(success=True, output_message="")
   ```
4. **Registro automático:** o `CommandRegistry` descobre as subclasses de `BaseSlashCommand` dos módulos de categoria.

---

## 3. Como Construir uma Nova Sub-tela ou Tela Modal (Ex: `/config`, `/models`)

Ao construir qualquer tela interativa:

1. **Siga o Blueprint Modal Obrigatório de [`CLI_DESIGN_SYSTEM.md`](CLI_DESIGN_SYSTEM.md):**
   - Borda externa arredondada fina (`╭──╮` / `╰──╯`) na cor `border_subtle` (`#262F3D`).
   - Título em negrito na cor `accent_cyan` (`#00D2FF`).
   - Se for master-detail (como `/config`): categorias na coluna esquerda com indicador ativo `● `, opções na coluna direita.
2. **Atalhos Obrigatórios de Navegação:**
   - `↑` e `↓`: movimentação entre opções.
   - `Tab`: alternância entre painéis/colunas.
   - `Enter` ou `Espaço`: seleção ou confirmação.
   - `Esc` ou `q`: fechamento e retorno seguro ao terminal principal.
3. **Nunca trave o terminal:** Sempre trate `KeyboardInterrupt` (`Ctrl+C`) e `EOFError` graciosamente, retornando ao chat principal sem derrubar o processo.

---

## 4. Checklist Obrigatório Antes de Concluir Tarefas de TUI

Antes de declarar que uma tarefa na CLI está concluída, você DEVE rodar as seguintes verificações:

- [ ] Execute `grep -r -E '[\U00010000-\U0010ffff]' src/` e garanta que nenhum emoji novo foi introduzido em arquivos de interface.
- [ ] Execute `uv run pytest tests/unit/test_cli.py tests/unit/test_prompt_session.py tests/unit/test_status_bar.py tests/unit/test_completer.py`.
- [ ] Garanta que todas as cores utilizadas pertençam ao dicionário oficial [`ORION_COLORS`](file:///home/danieldev/orion-agent/src/orion/tui/theme.py).
