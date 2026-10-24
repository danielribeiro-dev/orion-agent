# ORION-Agent — TUI Design System & Dinâmica de Terminal

> Especificação da interface interativa de terminal (TUI) do ORION, inspirada nas melhores práticas de ferramentas como Antigravity CLI e Claude Code.

---

## 1. Princípios da Experiência do Terminal

1. **Fluidez e Não Bloqueio**:
   - Streaming de respostas com renderização de Markdown em tempo real.
   - Indicadores visuais sutis (spinners assíncronos) quando o modelo ou ferramenta estiver processando.
2. **Alta Densidade de Informação sem Poluição**:
   - Diffs com sintaxe colorida destacando adições em verde suave e remoções em vermelho suave.
   - Colapso automático de logs longos (ex: saída de 100 linhas de compilação ou testes é resumida com opção de expandir).
3. **Controle Total de Autonomia e Segurança**:
   - Diálogos claros de permissão com contexto explícito da ação antes de executar:
     ```text
     ┌─ Confirmação de Ação Requerida (Nível 2) ──────────────────────────┐
     │ Comando: rm -rf ./tmp/cache_build                                  │
     │ Motivo:  Liberar espaço em disco solicitado pelo usuário           │
     │ Escopo:  Diretório local temporário                                │
     ├────────────────────────────────────────────────────────────────────┤
     │ [Y] Executar uma vez   [A] Permitir nesta sessão   [N] Cancelar     │
     └────────────────────────────────────────────────────────────────────┘
     ```

---

## 2. Slash Commands Dinâmicos (`/`)

O sistema de comandos por barra (`/`) permite disparar rotinas do agente ou alternar configurações com facilidade.

### 2.1 Comandos Nativos (Built-in)
- `/plan <objetivo>`: Entra no modo de planejamento estrito (cria plano antes de executar ações).
- `/compact`: Força a compactação e sumarização da sessão atual, liberando a janela de contexto.
- `/timeline`: Exibe a árvore cronológica de eventos, branches ativas e checkpoints recentes.
- `/branch <nome>`: Cria ou alterna para uma ramificação de contexto isolada para um projeto ou tarefa.
- `/merge`: Sintetiza a branch atual e consolida o checkpoint na Main Timeline.
- `/config`: Abre o menu interativo de configurações (autonomia, provedores, quotas, voz).
- `/cost`: Exibe o painel de consumo de tokens e custos em USD/BRL do dia e do mês.
- `/clear`: Limpa a visualização da tela sem apagar a memória da sessão.
- `/help`: Lista todos os comandos disponíveis e atalhos.

### 2.2 Comandos Dinâmicos Customizados pelo Usuário
O ORION descobre comandos adicionais automaticamente em:
- Global: `~/.orion/commands/<nome>.md` ou `.py`
- Projeto: `.orion/commands/<nome>.md`

Ao digitar `/` no prompt, um menu de autocomplete flutuante é exibido com a lista de comandos e suas descrições.

---

## 3. Menções Especiais (`@` Files e `#` Contexts)

- `@<caminho/arquivo>`: Injeta o conteúdo ou caminho do arquivo diretamente no contexto da mensagem.
- `#memory`: Força a busca explícita na memória de longo prazo sobre o termo subsequente.
- `#web`: Força busca em tempo real na internet.

---

## 4. Stack Tecnológica da Interface

- **Renderizador de TUI:** [Rich](https://github.com/Textualize/rich) para componentes visuais, tabelas, diffs e Markdown.
- **Gerenciador de Input / Prompt:** [Prompt Toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit) para histórico de comandos, keybindings, autocomplete e multiline input.
- **TUI Completa (Fase Avançada):** [Textual](https://github.com/Textualize/textual) para dashboards e monitores em tela cheia.
