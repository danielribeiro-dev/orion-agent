# Sprint — [v0.4.0] Sprint 1: Stream CLI Foundation, Design System & Banner Adaptativo

> **Status:** 📋 Pronto para Execução (Congelado)  
> **Versão Relacionada:** v0.4.0 (High-Performance Stream CLI, Slash Commands & Native MCP)  
> **Responsável / Agente:** Daniel Dev & Antigravity (Pair Programming com Gemini 3.8 Flash High)  
> **Data de Início:** Próxima Sessão  
> **Data de Conclusão:** —  
> **Branch Alvo:** `version/v0.4.0`

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Construir a base do CLI de terminal oficial do O.R.I.O.N através do comando executável `orion-agent`, integrando a paleta oficial de cores **"Deep Cosmos & Glacial Platinum"** via `Rich.Theme`, o motor responsivo do banner ASCII da **Mão Cósmica com o Buraco Negro** (adaptável dinamicamente para 80, 120 e 200+ colunas sem qualquer estouro ou quebra de linha), o painel de cabeçalho de status da sessão (identidade, contas GitHub/Google conectadas e estado da governança PEP) e a barra de status inferior dinâmica com livro-razão financeiro (USD/BRL) e tokens consumidos.
* **Dependências Prévias:** v0.3.0 estável (Model Gateway, métricas de custos em `metrics.db` e 838 testes passando).
* **Entregável Verificável:** Invocação de `orion-agent` no terminal exibindo o cabeçalho oficial com gradiente cósmico cyan/azul sem flickering, badges de status perfeitamente alinhados e barra inferior renderizada com zero estouro de largura em qualquer emulador de terminal (Ghostty, Kitty, WezTerm, Alacritty, GNOME Terminal).

---

## 2. Contexto de Engenharia & Filosofia Humana

### Por que esta sprint é vital para o Gemini 3.8 Flash (High)?
A primeira impressão de autoridade de um agente de IA reside no primeiro milissegundo de contato com o desenvolvedor. Se o terminal apresentar arte ASCII truncada, cores que ferem os olhos, flickering na tela ou quebra de linha de caracteres, a percepção de excelência é imediatamente danificada. 

O padrão que buscamos iguala e supera o **Claude Code** da Anthropic e o **Google Antigravity CLI**:
1. **Zero Flickering:** Nunca usar comandos de limpeza de tela brutos (`clear` ou `os.system("clear")`). Apenas renderização atômica Rich com double buffering interno.
2. **Rolagem Nativa do Terminal:** Nunca prender o usuário em buffers virtuais fechados de tela cheia. O `orion-agent` escreve para `stdout` contínuo, permitindo que a rodinha do mouse e o trackpad rolem normalmente por todo o histórico do shell.
3. **Conforto Ergonômico de 12h+:** Paleta calibrada com pretos cosmos profundos (`#0B0E14`), cinzas estelares (`#151B23`) e texto em branco glacial suave (`#E6EDF3`), eliminando o "efeito flashbang" do branco absoluto `#FFFFFF` e do preto `#000000`.

---

## 3. Representação Visual Humana (Wireframes ASCII Exatos)

O Gemini 3.8 Flash deve renderizar a interface mentalmente através destes três wireframes de referência:

### 📐 Cenário A: Terminal Padrão (80 Colunas — Modo Compacto / Laptop)
Em 80 colunas, a arte original de 248 colunas é recortada no núcleo do Buraco Negro e na palma da mão cósmica, combinada com a tipografia *Stellar Cyber Block*:

```text
╭──────────────────────────────────────────────────────────────────────────────╮
│  ██████╗ ██████╗ ██╗ ██████╗ ███╗   ██╗   O.R.I.O.N  v0.4.0                  │
│ ██╔═══██╗██╔══██╗██║██╔═══██╗████╗  ██║   Sovereign Cognitive Agent           │
│ ██║   ██║██████╔╝██║██║   ██║██╔██╗ ██║   https://github.com/danielribeiro-dev│
│ ╚██████╔╝██║  ██║██║╚██████╔╝██║ ╚████║                                      │
├──────────────────────────────────────────────────────────────────────────────┤
│ ● GATEWAY: Online (Auto-Routing)       ● MODEL: claude-3-7-sonnet-thinking   │
│ ● REASONING: HIGH (Depth Thinking)     ● AUTH: GitHub [@danielribeiro-dev]   │
│ ● MEMORY: 5 Spheres (838 Events)       ● PEP: Level 2 (Supervised)           │
╰──────────────────────────────────────────────────────────────────────────────╯
  Dica: Digite / para comandos rápidos, @ para anexar arquivos ou pergunte livremente.
```

### 📐 Cenário B: Terminal Standard de Desenvolvimento (120 Colunas — Modo Padrão)
Em 120 colunas, há espaço para a composição visual completa da fenda cósmica e horizonte de eventos em gradiente TrueColor:

```text
╭──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│  O.R.I.O.N  v0.4.0 │ Operational Reasoning & Intelligence Orchestration Network                                      │
│  "Non Ducor, Duco — The Sovereign Cognitive Operating Partner"                                                       │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  ● STATUS: ONLINE (Cloud Gateway)        ● REASONING: HIGH (Depth Thinking Active)                                   │
│  ● MODEL: claude-3-7-sonnet-thinking     ● GATEWAY: Auto-Routing (Fast/Deep Dynamic)                                 │
│  ● AUTH: GitHub [@danielribeiro-dev]     ● GOOGLE: daniel.dev@gmail.com (OAuth Connected)                            │
│  ● TIMELINE: 838 events in SQLite WAL    ● MEMORY: 5 Spheres Active (FTS5 + ONNX Embeddings)                         │
│  ● PEP GOVERNANCE: Level 2 (Supervised)  ● WORKSPACE: /home/danieldev/orion-agent                                    │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
  Dica: Digite / para comandos rápidos, @ para anexar arquivos locais ou pressione Ctrl+C para cancelar.
```

### 📐 Cenário C: Barra de Status Dinâmica (Fixada na Base / Atualizada por Turno)
```text
[claude-3-7-sonnet] [Thinking: HIGH] [PEP: Level 2] │ Tokens: 1,840 in / 420 out │ $0.0031 USD (~R$ 0,018) │ Ready ●
```

---

## 4. O Design System de Cores Oficial ("Deep Cosmos & Glacial Platinum")

As constantes exatas a serem implementadas em `src/orion/tui/theme.py`:

```python
"""Design System Oficial do O.R.I.O.N — Paleta Deep Cosmos & Glacial Platinum."""

ORION_COLORS = {
    # Fundos e Superfícies
    "bg_canvas": "#0B0E14",        # Fundo do terminal (Preto Cosmos Suave)
    "surface_panel": "#151B23",    # Fundo de cards, caixas e diffs (Grafite Estelar)
    "border_subtle": "#262F3D",    # Bordas e separadores discretos
    
    # Textos e Leitura Prolongada (WCAG AAA > 13:1)
    "text_primary": "#E6EDF3",     # Branco Glacial para respostas do agente
    "text_dim": "#8B949E",         # Cinza Titânio Fosco para metadados e logs
    "text_user": "#F0F6FC",        # Branco Iluminado para input do usuário
    
    # Identidade Cósmica do ORION
    "accent_cyan": "#00D2FF",      # Cyan Cósmico (Buraco Negro, logos e badges)
    "accent_blue": "#3A7BD5",      # Azul Órion Profundo (links e modos)
    
    # Acentos Semânticos Funcionais
    "diff_add": "#3FB950",         # Verde Aurora Suave (Linhas adicionadas)
    "diff_del": "#F85149",         # Vermelho Alerta Suave (Linhas removidas)
    "pep_warn": "#D29922",         # Âmbar de Ignição (Avisos de permissão PEP)
    "status_ok": "#2EA043",        # Verde de Conectividade Online
    "status_offline": "#DA3633",   # Vermelho de Modo Offline / Failover
}
```

---

## 5. Arquitetura de Módulos & Arquivos Afetados

```
src/orion/
├── cli.py                             # Atualização: Ponto de entrada oficial `orion-agent`
└── tui/
    ├── __init__.py                    # Exportação pública dos componentes TUI
    ├── theme.py                       # NOVO: Mapeamento da paleta para rich.theme.Theme
    ├── console.py                     # NOVO: Singleton get_console() configurado com o tema
    ├── banner.py                      # NOVO: BannerRenderer responsivo (80, 120 e 200+ cols)
    └── status_bar.py                  # NOVO: SessionStatusBar Pydantic v2 + renderizador de badges
tests/
└── unit/
    ├── test_theme.py                  # NOVO: Teste de carregamento do tema e paleta de cores
    ├── test_banner.py                 # NOVO: Teste de redimensionamento e recorte em 80/120/200 cols
    └── test_status_bar.py             # NOVO: Teste de formatação monetária e montagem de badges
```

---

## 6. Contratos de Código & Assinaturas Tipadas

### 6.1 `src/orion/tui/theme.py`
```python
from rich.theme import Theme

def get_orion_theme() -> Theme:
    """Retorna a instância Theme do Rich com todos os estilos semânticos do ORION."""
    ...
```

### 6.2 `src/orion/tui/console.py`
```python
from rich.console import Console

def get_console(force_terminal: bool = None) -> Console:
    """Retorna ou cria o console Rich compartilhado com o tema oficial configurado."""
    ...
```

### 6.3 `src/orion/tui/banner.py`
```python
from pathlib import Path
from typing import Optional
from rich.console import RenderableType

class BannerRenderer:
    def __init__(self, ascii_art_path: Optional[Path] = None):
        """Inicializa o renderizador carregando docs/design/ascii-art.txt."""
        ...

    def render(self, terminal_width: Optional[int] = None) -> RenderableType:
        """Renderiza o banner adaptativo para a largura especificada ou detectada.
        
        Regras de Largura:
        - width < 100: Retorna o layout compacto (Stellar Cyber Block + Badges de 2 colunas).
        - width >= 100: Retorna o layout standard/amplo com gradiente cyan/azul cósmico.
        """
        ...
```

### 6.4 `src/orion/tui/status_bar.py`
```python
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional
from rich.console import RenderableType

class ReasoningEffort(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    OFF = "OFF"

class SessionStatusBar(BaseModel):
    is_online: bool = True
    model_name: str = "claude-3-7-sonnet-thinking"
    reasoning_effort: ReasoningEffort = ReasoningEffort.HIGH
    pep_level: int = Field(default=2, ge=0, le=3)
    github_user: Optional[str] = None
    google_account: Optional[str] = None
    events_count: int = 0
    workspace_path: str = ""
    session_tokens_in: int = 0
    session_tokens_out: int = 0
    session_cost_usd: float = 0.0
    usd_to_brl_rate: float = 5.75

    @property
    def session_cost_brl(self) -> float:
        return self.session_cost_usd * self.usd_to_brl_rate

    def render_header_panel(self, width: int = 80) -> RenderableType:
        """Gera o painel de cabeçalho formatado em Rich com bordas arredondadas."""
        ...

    def render_bottom_bar(self, width: int = 80) -> RenderableType:
        """Gera a linha de status inferior com tokens e custos em USD e BRL."""
        ...
```

---

## 7. Passo a Passo de Implementação Cirúrgica

1. **Passo 1 — Entrypoint no `pyproject.toml`:**
   Configurar `orion-agent = "orion.cli:main"` na seção `[project.scripts]` e verificar que `pip install -e .` ou `uv pip install -e .` reconhece o binário.

2. **Passo 2 — Criação de `src/orion/tui/theme.py` e `console.py`:**
   Mapear as cores da paleta Deep Cosmos para estilos Rich nomeados (`orion.cyan`, `orion.text`, `orion.panel`, etc.) e inicializar a instância compartilhada `Console(theme=...)`.

3. **Passo 3 — Algoritmo de Recorte e Gradiente em `banner.py`:**
   - Carregar o arquivo `docs/design/ascii-art.txt`.
   - Se a largura for $< 100$ colunas, utilizar o logo sólido `Stellar Cyber Block` com moldura arredondada para garantir que nenhuma linha estoure.
   - Se a largura for $\ge 100$ colunas, carregar a arte do horizonte de eventos e aplicar gradiente de cor suave (de `#00D2FF` para `#3A7BD5`).

4. **Passo 4 — Extração Dinâmica de Identidade em `status_bar.py`:**
   - Obter usuário do git via `git config user.name` ou `gh api user` com fallback silencioso.
   - Extrair contagem de eventos da Timeline SQLite WAL (`~/.orion/timeline.db`).
   - Formatar valores de custo com precisão de 4 casas decimais para USD e 3 casas para BRL.

5. **Passo 5 — Integração com o Entrypoint `orion.cli:main`:**
   Ao rodar `orion-agent`, renderizar o banner, o cabeçalho e a barra de status sem travamentos de thread.

6. **Passo 6 — Bateria de Testes Automatizados:**
   Criar `tests/unit/test_theme.py`, `tests/unit/test_banner.py` e `tests/unit/test_status_bar.py`.

---

## 8. Critérios de Aceite & Definition of Done (DoD)

### Cenários de Teste Obrigatórios
- **CA-01 (Larguras de Terminal):** Testar renderização com larguras emuladas de 60, 80, 100, 120 e 200 colunas. Em nenhuma largura deve ocorrer `IndexError` ou linhas que excedam o tamanho solicitado.
- **CA-02 (Validação Monetária):** Com `session_cost_usd = 0.0100` e taxa de `5.75`, validar que a barra exibe `$0.0100 USD` e `R$ 0,058`.
- **CA-03 (Fallback de Identidade):** Se o ambiente não possuir Git ou conexão externa, os badges devem exibir valores de fallback graciosos sem disparar exceções não tratadas.
- **CA-04 (Zero Quebras ANSI):** Validar que a saída gerada não contém códigos de escape ANSI quebrados ou incompletos.

### Definition of Done (DoD)
- [ ] Binário `orion-agent` configurado no `pyproject.toml`.
- [ ] Módulos `theme.py`, `console.py`, `banner.py` e `status_bar.py` implementados com tipagem Pydantic v2 estrita.
- [ ] 100% dos testes unitários passando em `pytest tests/unit/test_banner.py tests/unit/test_status_bar.py tests/unit/test_theme.py`.
- [ ] Cobertura de testes dos novos módulos $\ge 90\%$.
- [ ] Zero regressão nos 838 testes existentes das versões v0.1.0 a v0.3.0.
- [ ] Documentação de progresso atualizada em `.claudex/progress.md`.
