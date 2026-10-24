# ORION-Agent — TUI Design System & Dinâmica de Terminal

> Especificação da interface interativa de terminal (CLI/TUI) do ORION, orientada à máxima produtividade e fluidez no fluxo de trabalho do desenvolvedor (inspirada no padrão de excelência de Claude Code e Google Antigravity).

---

## 1. Princípios da Experiência do Desenvolvedor

1. **Fluidez e Não Bloqueio (Rolagem Nativa do Terminal):**
   - O terminal rola solto. O desenvolvedor utiliza o trackpad ou a rodinha do mouse naturalmente, sem janelas ou buffers virtuais travados.
   - Streaming de respostas com renderização de Markdown em tempo real via `Rich.Live`.
   - Indicadores visuais assíncronos não bloqueantes (*spinners*) enquanto ferramentas ou chamadas de modelo estão processando.

2. **Alta Densidade de Informação com Diffs Cirúrgicos:**
   - Modificações de código são apresentadas em painéis de diff cirúrgicos formatados em Rich (verde suave para adições, vermelho suave para remoções), nunca através de dumps brutos de arquivos inteiros.
   - Colapso automático de logs longos (ex: saída de 100 linhas de compilação ou testes é resumida com opção de expandir).

3. **Barra de Entrada Inteligente (Smart Bottom Input):**
   - Cursor responsivo na base do terminal gerenciado por `prompt_toolkit`.
   - Menu flutuante de autocompletar ao digitar `/`, com busca fuzzy e descrições dos comandos.
   - Suporte a `@` para anexar ou citar arquivos locais com expansão automática de caminho.
   - Status bar inferior persistente exibindo:
     `[ MODE: ONLINE ]──[ MODEL: claude-3-7-sonnet ]──[ THINKING: HIGH ]──[ SESSION: $0.042 (~R$ 0,24) ]`

4. **Controle Total de Autonomia e Segurança (PEP):**
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

## 2. O Cabeçalho de Inicialização (*Splash Banner*)

O cabeçalho renderiza a arte ASCII da **Mão com o Buraco Negro** ([`docs/design/ascii-art.txt`](ascii-art.txt)) com gradiente cyan/azul cósmico, adaptando-se dinamicamente à largura do terminal:

```text
╭─────────────────────────────────────────────────────────────────────────────────────────────╮
│  O.R.I.O.N  v0.4.0 │ Operational Reasoning & Intelligence Orchestration Network            │
│  "Non Ducor, Duco — The Sovereign Cognitive Operating Partner"                             │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│  ● STATUS: ONLINE (Cloud Gateway)      ● REASONING: HIGH (Depth Thinking Active)            │
│  ● MODEL: claude-3-7-sonnet-thinking   ● GATEWAY: Auto-Routing (Fast/Deep Dynamic)          │
│  ● AUTH: GitHub [@danielribeiro-dev]   ● GOOGLE: daniel.dev@gmail.com (OAuth Connected)     │
│  ● TIMELINE: 42 events today           ● MEMORY: Triple Store Active (FTS5 + ONNX + 18 Facts│
│  ● PEP GOVERNANCE: Level 2 (Supervised)● WORKSPACE: /home/danieldev/orion-agent             │
╰─────────────────────────────────────────────────────────────────────────────────────────────╯
  Dica: Digite / para comandos rápidos, @ para anexar arquivos ou mencione instruções livremente.
```

---

## 3. Catálogo Oficial de Slash Commands (`/`)

Adotamos exclusivamente comandos de alto valor para o desenvolvimento:

| Categoria | Comando | Descrição Operacional |
| :--- | :--- | :--- |
| **Cognitivo & Raciocínio** | `/plan <meta>` | Ativa o modo planejamento estrito: pesquisa, gera artefato formal e colhe aprovação. |
| | `/goal <meta>` | Dispara execução autônoma prolongada com auto-recuperação (*Self-Healing*). |
| | `/grill-me` | Entrevista investigativa (Socrática) para esclarecer requisitos antes do código. |
| | `/review` | Revisão crítica de código e segurança nos diffs recentes. |
| **Memória & Habilidades** | `/learn` | Auto-destilação: compila a solução da tarefa em uma nova skill `SKILL.md`. |
| | `/memory` | Inspeciona a Memória Tríplice (fatos confirmados, vetores e `MEMORY.md`). |
| | `/timeline` | Exibe a linha do tempo contínua persistente no SQLite com Day Markers. |
| | `/recall <termo>` | Executa busca profunda híbrida RRF para resgatar decisões ou bugs passados. |
| **Contexto & Branches** | `/compact [foco]` | Compactação inteligente preservando *vital tail* e arquivos ativos. |
| | `/context` | Gráfico visual de barras no terminal exibindo a composição da janela de tokens. |
| | `/branch <nome>` | Ramificação de contexto isolada para investigações profundas. |
| | `/merge` | Síntese de checkpoint de 3 a 5 linhas comitada na Main Timeline. |
| **Operação & Governança** | `/diff` | Painel colorido syntax-highlighted de todas as modificações da sessão. |
| | `/undo` | Rollback atômico da última alteração via git checkpoint. |
| | `/run <cmd>` | Execução cirúrgica de comando no SO via PEP. |
| | `/doctor` | Diagnóstico de saúde do ambiente (Python, pacotes, daemon, Ollama, chaves). |
| | `/cost` | Livro-razão financeiro com tokens de entrada, saída, cache e total em USD e BRL. |
| | `/config` | Painel interativo para alternar provedores, modelos, modo auto/fixed e PEP. |
| | `/mcp` | Gerencia conexões e ferramentas do Model Context Protocol (stdio / SSE). |
| | `/voice` | Ativa ou silencia o daemon de presença ambiente e voz headless. |
| | `/clear` | Limpa a visão do terminal sem apagar o histórico de memória. |
| | `/help` | Guia completo de comandos e dicas rápidas de atalhos de teclado. |

---

## 4. Menções Especiais (`@` Files)

- `@<caminho/arquivo>`: O `prompt_toolkit` autocompleta nomes de arquivos locais respeitando `.gitignore` e anexa o arquivo ao contexto imediato do turno.

---

## 5. Stack Tecnológica Homologada

- **Gerenciador de Input / Prompt:** [Prompt Toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit) para histórico de comandos, atalhos readline/vi, autocomplete flutuante (`/` e `@`) e barra de status inferior.
- **Renderizador de Markdown & Diffs:** [Rich](https://github.com/Textualize/rich) para streaming (`Live`), tabelas, painéis formatados, banners e diffs cirúrgicos com realce sintático.
- **Nota sobre Interfaces Full-Screen (eDEX-UI):** Descartadas como interface padrão para manter 100% de fluidez e produtividade de digitação no terminal diário. Qualquer interface visual rica e cinematográfica fica postergada para um aplicativo visual dedicado pós-v1.0.0.
