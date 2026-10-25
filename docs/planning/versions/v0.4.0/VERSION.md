# Spec — [v0.4.0] High-Performance Stream CLI, Slash Commands & Native MCP

> **Status:** 📋 Especificação Completa e Congelada para Execução após a v0.3.0  
> **Criada em:** 2026-10-24  
> **Concluída em:** —  
> **Autor(es):** Daniel Dev & Antigravity (Pair Programming)  
> **Branch:** `version/v0.4.0`  

---

## 1. Visão Geral & Motivação

### 1.1 Objetivo
Construir a camada de interface e experiência de desenvolvimento do **O.R.I.O.N**, entregando um **Stream CLI** de altíssima performance inspirado no padrão de excelência de mercado do **Claude Code** e **Google Antigravity**:
1. **Comando Oficial `orion-agent`:** Ponto de entrada CLI rápido e leve para o desenvolvedor (reservando o identificador `orion` para a futura interface gráfica eDEX/Desktop pós-v1.0.0).
2. **Splash Banner Dinâmico:** Exibição da arte ASCII oficial da **Mão com o Buraco Negro** adaptativa (80, 120 e 200+ colunas), com badges de status (Online/Local), identificação de contas (GitHub/Google) e estado da governança PEP.
3. **Barra de Entrada Inteligente (`prompt_toolkit`):** Autocomplete flutuante de Slash Commands (`/`), injeção rápida de arquivos via `@` com resolução respeitando `.gitignore`, atalhos de navegação e barra de status inferior dinâmica (Modelo ativo, Esforço de Raciocínio `HIGH/MED/LOW`, e custos acumulados em USD/BRL).
4. **Streaming Vivo & Diffs Cirúrgicos (`rich`):** Renderização de Markdown em tempo real via `Rich.Live`, indicadores visuais assíncronos não bloqueantes (*spinners*) e painéis de diff coloridos (verde/vermelho) para modificações de código.
5. **Catálogo Oficial dos 20 Slash Commands (`/`):** Implementação dos comandos cognitivos, de memória, branches, operação e custos.
6. **Cliente Nativo do Model Context Protocol (MCP):** Conexão universal stdio e SSE com servidores externos de ferramentas e dados.

### 1.2 Por que agora?
Após as fundações do ReAct Loop (v0.1.0), da Memória Tríplice Contínua (v0.2.0) e do Gateway de Modelos e Custos (v0.3.0), o ORION atinge a maturidade para oferecer a melhor experiência de terminal do mercado, unindo fluidez e velocidade à autoridade estética.

### 1.3 O que NÃO é escopo (anti-metas)
- Não construir uma interface TUI travada em tela cheia no terminal estilo eDEX (ideia descartada do CLI para preservar rolagem nativa e velocidade).
- Não plugar hardware ou pipelines de áudio/voz nativo no CLI (escopo da v0.5.0; o CLI apenas oferece o comando `/voice` para controlar o daemon).
- Não implementar sandbox Bubblewrap nesta versão (escopo da v1.5.0).

---

## 2. Decisões Arquiteturais & Diretrizes de Design (ADRs)

- **ADR-003:** Presença Ambiente Headless com Interface Sob Demanda.
- **ADR-014:** Comando Oficial `orion-agent` para o Stream CLI e Reserva de `orion` para Interface Gráfica eDEX/Desktop posterior.
- **ADR-015:** Stack Tecnológica do Stream CLI: `prompt_toolkit` (Buffer, histórico, autocomplete `/` e `@`) + `Rich` (Streaming `Live`, diffs cirúrgicos e banners adaptativos).
- **ADR-016:** Catálogo Oficial de Slash Commands (`/`) focado em produtividade e interoperabilidade de mercado.

---

## 3. Divisão em Sprints & Entregáveis

| Sprint | Nome da Sprint | Objetivo Principal | Documento | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Sprint 1** | Stream CLI, Banner & Status Line | Ponto de entrada `orion-agent`, arte ASCII da Mão Cósmica com Buraco Negro adaptativa e barra de status dinâmica | [`sprints/sprint-1.md`](sprints/sprint-1.md) | 📋 Planejado |
| **Sprint 2** | Prompt Interativo & Autocomplete | `prompt_toolkit` com histórico persistente, autocomplete flutuante para `/` e anexo de arquivos com `@` | [`sprints/sprint-2.md`](sprints/sprint-2.md) | 📋 Planejado |
| **Sprint 3** | Streaming Vivo, Diffs & Comandos | Streaming contínuo via `Rich.Live`, painéis de diff cirúrgico e o catálogo oficial dos 20 Slash Commands | [`sprints/sprint-3.md`](sprints/sprint-3.md) | 📋 Planejado |
| **Sprint 4** | Native MCP Client & Integração PEP | Cliente nativo do Model Context Protocol (stdio & SSE) com auditoria de segurança PEP | [`sprints/sprint-4.md`](sprints/sprint-4.md) | 📋 Planejado |

---

## 4. Arquitetura Alvo & Componentes Afetados

```
src/orion/
├── cli.py                             # Entrypoint do binário `orion-agent`
├── tui/
│   ├── __init__.py
│   ├── banner.py                      # Renderizador dinâmico da Mão Cósmica (80/120/200 cols)
│   ├── console.py                     # Instância compartilhada do Rich Console com tema Cyan/Blue
│   ├── prompt.py                      # Buffer de input do prompt_toolkit com bottom status bar
│   ├── completer.py                   # Autocomplete flutuante: / para comandos e @ para arquivos
│   ├── stream_renderer.py             # Streaming em tempo real de Markdown via Rich.Live
│   ├── diff_viewer.py                 # Painel visual de diffs cirúrgicos syntax-highlighted
│   ├── status_bar.py                  # Badges dinâmicos: Modelo, Thinking, Custos, Status Online/Local
│   └── commands/                      # Catálogo modular de Slash Commands (/)
│       ├── __init__.py
│       ├── base.py                    # Classe abstrata BaseSlashCommand
│       ├── registry.py                # Despachante e registro de comandos
│       ├── plan.py                    # /plan
│       ├── goal.py                    # /goal
│       ├── grill_me.py                # /grill-me
│       ├── review.py                  # /review
│       ├── learn.py                   # /learn
│       ├── memory.py                  # /memory
│       ├── timeline.py                # /timeline
│       ├── compact.py                 # /compact
│       ├── context.py                 # /context
│       ├── branch.py                  # /branch e /merge
│       ├── diff.py                    # /diff e /undo
│       ├── cost.py                    # /cost
│       ├── doctor.py                  # /doctor
│       └── mcp.py                     # /mcp
└── mcp/
    ├── __init__.py
    ├── client.py                      # Cliente assíncrono nativo MCP (stdio e SSE)
    ├── transport.py                   # Gerenciamento de subprocessos e streams
    └── adapter.py                     # Conversão de ferramentas MCP para BaseTool do ORION
```

---

## 5. Matriz de Critérios de Aceite da Versão (DoD Global)

| ID | Cenário | Comportamento Esperado | Como Validar | Status |
|:---|:---|:---|:---|:---|
| CA-01 | Comando `orion-agent` | Inicializa o CLI instantaneamente em $< 100\text{ ms}$ sem travamento | `orion-agent --help` / `orion-agent` | ⏳ Pendente |
| CA-02 | Banner Adaptativo | Mão Cósmica e Buraco Negro renderizam sem quebra de linha em 80, 120 e 200+ cols | `pytest tests/unit/test_banner.py` | ⏳ Pendente |
| CA-03 | Barra de Status Dinâmica | Exibe Modelo, Esforço de Raciocínio, Status Online/Local e Custos em USD/BRL | `pytest tests/unit/test_status_bar.py` | ⏳ Pendente |
| CA-04 | Autocomplete de Comandos e Arquivos | Menu flutuante filtra comandos ao digitar `/` e arquivos locais ao digitar `@` | `pytest tests/unit/test_completer.py` | ⏳ Pendente |
| CA-05 | Streaming Vivo em Markdown | Respostas do modelo surgem em Markdown formatado sem quebrar o scroll nativo | `pytest tests/unit/test_stream_renderer.py` | ⏳ Pendente |
| CA-06 | Diffs Cirúrgicos | Edições em arquivos exibem blocos de diff syntax-highlighted | `pytest tests/unit/test_diff_viewer.py` | ⏳ Pendente |
| CA-07 | Catálogo de Slash Commands | Todos os comandos disparam suas rotinas e obedecem às políticas do PEP | `pytest tests/unit/test_slash_commands.py` | ⏳ Pendente |
| CA-08 | Cliente MCP Nativo | Conecta a servidores stdio/SSE, descobre ferramentas e executa tool calls com timeout | `pytest tests/unit/test_mcp_client.py` | ⏳ Pendente |
| CA-09 | Cobertura de Testes | Suíte completa da v0.4.0 passando com cobertura $\ge 85\%$ | `pytest --cov=src/orion` | ⏳ Pendente |

---

## 6. Checklist de Conclusão da Spec (Congelamento)

- [x] Especificação técnica e arquitetural da v0.4.0 alinhada e aprovada pelo usuário.
- [x] As 4 sprints da v0.4.0 detalhadas e congeladas em `docs/planning/versions/v0.4.0/sprints/`.
- [ ] Implementação das 4 sprints concluída com testes automatizados.
- [ ] Bateria de testes com cobertura $\ge 85\%$.
- [ ] Tag Git `v0.4.0` criada.
