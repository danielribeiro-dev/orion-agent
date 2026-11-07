# Sprint — [v0.4.0] Sprint 3: Refinamento Estético da CLI, Geometria Anti-Emoji & Dynamic Prompt Engine

> **Status:** ✔ Concluída  
> **Versão Relacionada:** v0.4.0 (High-Performance Stream CLI, Slash Commands & Native MCP)  
> **Responsável / Agente:** Daniel Dev & Antigravity (Pair Programming com Gemini 3.8 Flash High)  
> **Data de Início:** 27/10/2026  
> **Data de Conclusão:** 27/10/2026  
> **Branch Alvo:** `version/v0.4.0`

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Eliminar as falhas estéticas e bugs visuais da CLI identificados no uso real, alinhando a experiência do desenvolvedor com o padrão de excelência de mercado (Claude Code, Google Antigravity e Hermes Agent):
  1. **Banimento Completo de Emojis:** Substituir todos os emojis na CLI, autocomplete e mensagens de sistema por glifos geométricos precisos do padrão monospace oficial (`❯`, `●`, `✔`, `✖`, `!`, `[PEP]`, `›`), eliminando de vez problemas de desalinhamento de largura (`wcwidth`) e conferindo estética técnica e sóbria de engenharia.
  2. **Correção do Bug das Linhas do Campo de Texto (Input Engine):** Eliminar a injeção estática de janelas `char="─"` e a colisão de scrollback com o menu de autocomplete. Adotar o padrão minimalista estilo Claude Code / gh (`❯ `), cuja altura expande suavemente com multilinhas e retrai imediatamente para 1 linha ao apagar, com zero linhas fantasmas.
  3. **Correção da Barra de Status Inferior (Bottom Line):** Remover a faixa sólida colorida de fundo (`bg:surface_panel`) que atravessa toda a largura do terminal. Implementar uma linha de status sobre o fundo nativo do terminal, com textos atenuados e separadores discretos (`·` ou `│`).
  4. **Documentação Normativa Definitiva:** Criar a especificação mestra `docs/design/CLI_DESIGN_SYSTEM.md` e o manual prescritivo `docs/design/CLI_AGENT_RULES.md` para garantir que qualquer desenvolvedor ou agente de IA saiba exatamente como construir telas, modais e saídas sem inventar estilos da própria cabeça.
* **Dependências Prévias:** Sprint 1 e Sprint 2 concluídas (Estrutura do CLI, tema e prompt interativo com `prompt_toolkit`).
* **Entregável Verificável:** CLI executando com prompt limpo `❯ `, digitação de `/plan` e autocomplete operando sem duplicar linhas horizontais, rodapé discreto sem barra colorida sólida, ausência total de emojis na interface e suíte de testes passando.

---

## 2. Contexto de Engenharia & Filosofia

### Por que esta sprint é indispensável?
Uma CLI de agente de IA é o cartão de visitas e o ambiente onde o engenheiro passará horas diárias. 
1. **O problema do `wcwidth` dos emojis:** Emojis têm largura variável em diferentes emuladores de terminal (Kitty, WezTerm, Ghostty, Alacritty, GNOME Terminal). Tratá-los como símbolos de largura fixa causa quebras de colunas e efeitos de "cursor drift". A indústria de ferramentas sérias (Claude Code, Antigravity, Git, Docker) usa geometria monocromática e TrueColor precisa.
2. **O problema do scrollback do prompt:** A injeção de `Window(char="─")` diretamente no container do `prompt_toolkit`, combinada com menus flutuantes que empurram linhas para o histórico de rolagem do terminal, gera o bug onde linhas horizontais crescem e nunca voltam ao normal. O cursor limpo `❯ ` com tratamento dinâmico de multilinhas resolve a causa raiz de forma robusta e elegante.
3. **O problema da barra colorida pesada:** A barra inferior ocupando 100% da largura com cor sólida cria fadiga visual e poluição estética. O padrão moderno utiliza o fundo nativo do terminal com dados sutis e atenuados.

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Estado Inicial (Sprint 2) | Estado Final Esperado (Sprint 3 DoD) |
| :--- | :--- | :--- |
| **Uso de Emojis** | Emojis no catálogo de `/`, no status de memória e mensagens (`📋`, `🎯`, `🧠`, `⚠️`, `✅`) | **Zero emojis.** Padrão Unicode oficial: `❯ /plan`, `❯ /goal`, `● [Memory]`, `!`, `✔`, `✖`, `[PEP]` |
| **Linhas do Campo de Texto** | Linhas horizontais `─` fixas acima e abaixo que se multiplicavam ao autocompletar e não reduziam | Prompt minimalista estilo Claude Code / gh (`❯ `), expansão vertical dinâmica para multilinhas e retração imediata sem resíduos |
| **Barra de Status Inferior** | Faixa retangular sólida preenchendo toda a largura (`bg:surface_panel`) | Linha limpa sobre fundo transparente/nativa do terminal, separadores discretos (`·` ou `│`) e dados enxutos |
| **Diretrizes para Agentes** | Princípios dispersos em specs gerais | Documentos formais `CLI_DESIGN_SYSTEM.md` e `CLI_AGENT_RULES.md` congelados |

---

## 4. Escopo da Sprint

### ✅ No Escopo (In Scope)
- [x] Criação de `docs/design/CLI_DESIGN_SYSTEM.md` contendo a especificação visual e técnica completa (cores, glifos, wireframes de chat, modais como `/config`, seletor de modelos, autorização PEP e streaming).
- [x] Criação de `docs/design/CLI_AGENT_RULES.md` com as regras mandatárias para agentes de IA implementarem novos comandos e componentes.
- [x] Atualização de `docs/design/TUI_DESIGN_SYSTEM.md` e dos roadmaps de planejamento.
- [x] Refatoração de `src/orion/tui/completer.py`:
  - Substituição de todos os ícones de emojis em `OFFICIAL_SLASH_COMMANDS` por `❯` e `●`.
- [x] Refatoração de `src/orion/tui/prompt.py`:
  - Remoção de `top_tunnel` e `bottom_tunnel` injetados com `char="─"`.
  - Configuração do prompt minimalista com indicador `❯ ` em cyan.
  - Ajuste do `get_bottom_toolbar` e tabela de estilos para eliminar fundos sólidos (`bg:surface_panel` generalizado).
  - Configuração correta de reservas de menu e redimensionamento dinâmico.
- [x] Refatoração de `src/orion/tui/status_bar.py`:
  - Ajuste de `render_bottom_bar` para paleta atenuada e sem barras de fundo espessas.
- [x] Limpeza de emojis em arquivos de memória, governança e gateway (`src/orion/memory/file_syncer.py`, `src/orion/memory/hitl_telegram.py`, `src/orion/governance/nuclear.py`, `src/orion/governance/pep.py`, `src/orion/gateway/circuit_breaker.py`, `src/orion/cli.py`).
- [x] Atualização e expansão dos testes unitários em `tests/unit/test_prompt_session.py`, `tests/unit/test_status_bar.py`, `tests/unit/test_completer.py` e `tests/unit/test_cli.py`.

### 🚫 Fora de Escopo (Anti-Metas)
- Não implementar os 20 Slash Commands (escopo da Sprint 4).
- Não implementar streaming em tempo real `Rich.Live` e diffs de arquivos (escopo da Sprint 4).
- Não implementar conectores MCP (escopo da Sprint 5).
- Não configurar instalação global via script `curl | bash` neste momento (postergado para etapa posterior conforme decisão do desenvolvedor).

---

## 5. Arquitetura & Arquivos Afetados

```
docs/
├── design/
│   ├── CLI_DESIGN_SYSTEM.md           # [NOVO] Especificação mestra de design da CLI
│   ├── CLI_AGENT_RULES.md             # [NOVO] Regras e restrições obrigatórias para Agentes
│   └── TUI_DESIGN_SYSTEM.md           # [ATUALIZADO] Sincronização com o novo padrão
└── planning/
    ├── ROADMAP.md                     # [ATUALIZADO] Inserção da Sprint 3 no mapa
    └── versions/
        └── v0.4.0/
            ├── VERSION.md             # [ATUALIZADO] Nova grade de 5 sprints
            └── sprints/
                ├── sprint-3.md        # [NOVO] Esta sprint
                ├── sprint-4.md        # [RENOMEADO] Streaming Vivo & Diffs (antiga sprint-3)
                └── sprint-5.md        # [RENOMEADO] MCP Nativo (antiga sprint-4)

src/orion/
├── cli.py                             # Limpeza de emojis e símbolos de banner
└── tui/
    ├── completer.py                   # Catálogo com glifos ❯ e ● no lugar de emojis
    ├── prompt.py                      # Dynamic prompt ❯, remoção do túnel rígido e toolbar sem fundo
    └── status_bar.py                  # Barra de status sem blocos pesados
```

---

## 6. Critérios de Aceite & Verificação (Definition of Done)

| ID | Critério de Aceite | Como Validar |
| :--- | :--- | :--- |
| **CA-01** | Zero emojis no completer e nos comandos | `uv run pytest tests/unit/test_completer.py` |
| **CA-02** | Zero emojis nas mensagens de sistema, PEP e memória | Busca estática com regex de emojis em `src/orion/` retornando 0 ocorrências de emojis decorativos de interface |
| **CA-03** | Prompt com cursor `❯ ` e sem linhas horizontais fantasmas ao autocompletar `/plan` | Teste de unidade em `tests/unit/test_prompt_session.py` e validação interativa |
| **CA-04** | Barra inferior sem fundo sólido ocupando toda a tela | Teste de estilo em `tests/unit/test_status_bar.py` verificando ausência de `bg:surface_panel` contínuo |
| **CA-05** | Especificações de design completas e aprovadas | Existência e integridade de `docs/design/CLI_DESIGN_SYSTEM.md` e `docs/design/CLI_AGENT_RULES.md` |
| **CA-06** | Testes automatizados passando | `uv run pytest tests/unit/` com 100% de sucesso |
