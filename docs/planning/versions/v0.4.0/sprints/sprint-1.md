# Sprint — [v0.4.0] Sprint 1: Stream CLI, Banner & Status Line

> **Status:** 📋 Planejado  
> **Versão Relacionada:** v0.4.0 (High-Performance Stream CLI, Slash Commands & Native MCP)  
> **Responsável / Agente:** Daniel Dev & Antigravity  
> **Data de Início:** A definir (Fase 4)  
> **Data de Conclusão:** —  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Implementar o ponto de entrada oficial do CLI através do comando `orion-agent`, o motor de renderização responsiva do banner ASCII da **Mão com o Buraco Negro** (adaptável dinamicamente para larguras de 80, 120 e 200+ colunas sem quebras de linha), os badges informativos de contas vinculadas (GitHub/Google) e status de conectividade (Online/Local), e a barra de status dinâmica Rich fixada na base da interface.
* **Dependências Prévias:** v0.3.0 concluída (Model Gateway e métricas de custos em tempo real disponíveis).
* **Entregável Verificável:** Comando `orion-agent` executável no terminal, exibindo o cabeçalho oficial com gradiente cósmico cyan/azul, identificação das contas autenticadas e barra de status inferior dinâmica exibindo modelo ativo, nível de raciocínio (*Thinking: High/Med/Low*) e saldo de tokens da sessão em USD e BRL.

---

## 2. Contexto de Engenharia

* **Por que esta sprint existe:** Para criar uma identidade visual impactante e profissional que diferencie o ORION de qualquer outro agente do mercado desde o primeiro milissegundo de inicialização, preservando a autoridade estética sem sacrificar velocidade.
* **Como se encaixa na visão global:** Entrega a estrutura visual de cabeçalho e rodapé onde o loop interativo da Sprint 2 e os comandos da Sprint 3 serão acoplados.
* **Decisões arquiteturais associadas:** ADR-014 (Comando oficial `orion-agent`), ADR-015 (Stack Stream CLI com `Rich` e `prompt_toolkit`).

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Estado Inicial (Antes da Sprint) | Estado Final Esperado (DoD) |
| :--- | :--- | :--- |
| **Comando CLI** | Esqueleto básico | `orion-agent` operacional com resolução de argumentos Rich/Typer |
| **Banner ASCII** | Arquivo estático de 248 colunas | Renderizador adaptativo que ajusta a arte para a largura exata da janela |
| **Badges de Conta** | Inexistentes | Badges elegantes de GitHub (`@user`) e Google (`user@gmail.com`) no header |
| **Status Bar** | Inexistente | Barra inferior persistente com Modelo, Thinking Level e Custos (USD/BRL) |

---

## 4. Escopo da Sprint

### ✅ No Escopo (In Scope)
- [ ] Configuração do entrypoint `orion-agent = "orion.cli:main"` em `pyproject.toml`.
- [ ] Implementação de `BannerRenderer` em `src/orion/tui/banner.py`:
  - Carregamento de `docs/design/ascii-art.txt` e parsing de matriz de caracteres.
  - Detecção da largura do terminal via `shutil.get_terminal_size()`.
  - Renderização ampla ($\ge 140$ colunas): arte integral da mão e horizonte de eventos.
  - Renderização compacta (80 a 120 colunas): recorte centralizado no buraco negro e palma da mão com alta densidade e gradiente TrueColor.
- [ ] Implementação do painel de metadados em `src/orion/tui/status_bar.py`:
  - Extração do usuário GitHub ativo via `gh api user` ou `git config user.name`.
  - Extração da conta Google ativa via gcloud/OAuth caso configurada.
  - Status do modelo ativo (Online vs Local Ollama/vLLM) e nível de raciocínio (`HIGH`, `MEDIUM`, `LOW`, `OFF`).
- [ ] Renderização da barra inferior Rich com livro-razão de tokens ($ e R$) atualizado a cada turno.
- [ ] Testes automatizados de redimensionamento e formatação visual.

### 🚫 Fora de Escopo (Out of Scope / Anti-Metas)
- Não implementar loop de digitação e autocomplete interativo com `prompt_toolkit` (escopo da Sprint 2).
- Não registrar o catálogo completo de Slash Commands (escopo da Sprint 3).
- Não criar clientes MCP externos (escopo da Sprint 4).

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/
├── cli.py                             # Entrypoint do binário orion-agent
└── tui/
    ├── __init__.py
    ├── banner.py                      # Motor de banner responsivo da Mão Cósmica
    ├── console.py                     # Instância compartilhada do Rich Console
    └── status_bar.py                  # Badges de conta, modelo, thinking e custos
tests/
└── unit/
    ├── test_banner.py                 # Testes de redimensionamento em 80, 120 e 200 cols
    └── test_status_bar.py             # Testes de formatação dos badges e valores
```

---

## 6. Contratos de Código & Tipagem

```python
from enum import Enum
from pydantic import BaseModel
from typing import Optional

class ReasoningEffort(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    OFF = "OFF"

class SessionStatusBar(BaseModel):
    is_online: bool
    model_name: str
    reasoning_effort: ReasoningEffort
    github_user: Optional[str] = None
    google_account: Optional[str] = None
    session_tokens_in: int = 0
    session_tokens_out: int = 0
    session_cost_usd: float = 0.0
    session_cost_brl: float = 0.0
    pep_level: int = 2
```

---

## 7. Estratégia de Implementação (Passo a Passo)

1. **Passo 1:** Configurar o comando `orion-agent` no `pyproject.toml` e validar a invocação via terminal.
2. **Passo 2:** Desenvolver o módulo `src/orion/tui/banner.py` com o algoritmo de recorte e gradiente ANSI da Mão Cósmica com Buraco Negro.
3. **Passo 3:** Implementar o extrator de credenciais e contas locais em `src/orion/tui/status_bar.py`.
4. **Passo 4:** Criar a renderização do bloco de status do cabeçalho unindo status de gateway, memória e governança.
5. **Passo 5:** Escrever testes cobrindo variações de largura do terminal e montagem dos componentes visuais.

---

## 8. Testes Automatizados & Critérios de Aceite (DoD)

### Cenários de Teste Obrigatórios
- **Teste 1:** Emulação de terminal de 80 colunas renderiza o banner sem nenhuma linha quebrada ou estouro de margem.
- **Teste 2:** Emulação de terminal de 160 colunas renderiza a arte completa da Mão Cósmica com gradiente cyan/azul.
- **Teste 3:** Barra de status reflete com exatidão a conversão de câmbio USD/BRL e a contagem de tokens da sessão.

### Definition of Done (DoD)
- [ ] Comando `orion-agent` executável e funcional.
- [ ] Banner responsivo validado em 80, 120 e 200 colunas.
- [ ] Badges de autenticação e modelo renderizados perfeitamente.
- [ ] `pytest tests/unit/test_banner.py tests/unit/test_status_bar.py` passando com 100% de sucesso.
- [ ] Cobertura de testes dos módulos $\ge 90\%$.
- [ ] Documentação de progresso atualizada em `.claudex/progress.md`.
