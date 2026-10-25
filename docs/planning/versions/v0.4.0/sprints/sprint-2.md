# Sprint — [v0.4.0] Sprint 2: Prompt Interativo & Autocomplete

> **Status:** 📋 Planejado  
> **Versão Relacionada:** v0.4.0 (High-Performance Stream CLI, Slash Commands & Native MCP)  
> **Responsável / Agente:** Daniel Dev & Antigravity  
> **Data de Início:** A definir (Fase 4)  
> **Data de Conclusão:** —  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Implementar o motor de entrada interativa do desenvolvedor utilizando `prompt_toolkit`, dotando o CLI de histórico persistente de comandos (`~/.orion/history`), navegação avançada estilo Emacs/Vi, cancelamento gracioso de turnos com `Ctrl+C` (sem derrubar o agente), menu flutuante de autocompletar com busca difusa (*fuzzy*) ao digitar `/`, e autocompletar de caminhos de arquivos ao digitar `@` (respeitando `.gitignore` do workspace).
* **Dependências Prévias:** Sprint 1 concluída (Estrutura do CLI e tema visual Rich operacionais).
* **Entregável Verificável:** Módulos `src/orion/tui/prompt.py` e `src/orion/tui/completer.py` totalmente testados e integrados, proporcionando digitação veloz, fluida e contextual no terminal.

---

## 2. Contexto de Engenharia

* **Por que esta sprint existe:** Terminais nativos simples baseados em `input()` tradicional bloqueiam a thread, não possuem autocompletar flutuante, quebram com setas direcionais e não permitem anexar arquivos com facilidade. Para igualar e superar o Claude Code e Antigravity, o ORION precisa do `prompt_toolkit` configurado com completador assíncrono duplo (`/` e `@`).
* **Como se encaixa na visão global:** Entrega o teclado e o cérebro de entrada do desenvolvedor, tornando a digitação de instruções e comandos uma experiência ergonômica e ágil.
* **Decisões arquiteturais associadas:** ADR-015 (Stack Stream CLI com `prompt_toolkit` + `Rich`).

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Estado Inicial (Antes da Sprint) | Estado Final Esperado (DoD) |
| :--- | :--- | :--- |
| **Entrada de Texto** | `input()` síncrono padrão | Prompt assíncrono com `prompt_toolkit` e histórico persistente |
| **Autocomplete de Comandos** | Inexistente | Menu flutuante que abre ao digitar `/` com busca fuzzy e descrições |
| **Anexo de Arquivos** | Manual (digitar caminho) | Digitar `@` abre lista de arquivos locais filtrando pastas ignoradas |
| **Tratamento de Sinais** | `Ctrl+C` mata o processo | `Ctrl+C` interrompe apenas a inferência/execução atual e preserva a sessão |

---

## 4. Escopo da Sprint

### ✅ No Escopo (In Scope)
- [ ] Adicionar dependência `prompt-toolkit>=3.0.40` no `pyproject.toml`.
- [ ] Implementação de `OrionCompleter` em `src/orion/tui/completer.py`:
  - `SlashCommandCompleter`: detecta prefixo `/` e sugere os comandos cadastrados com descrições curtas e ícones.
  - `PathMentionCompleter`: detecta prefixo `@` e sugere arquivos e diretórios a partir da raiz do workspace ativo, ignorando `.git/`, `__pycache__/`, `node_modules/` e padrões de `.gitignore`.
- [ ] Implementação de `InteractivePrompt` em `src/orion/tui/prompt.py`:
  - Histórico persistente gravado em `~/.orion/history`.
  - Suporte a entrada multilinha (`Alt+Enter` ou colar código grande sem executar prematuramente).
  - Captura graciosa de `KeyboardInterrupt` (`Ctrl+C`) emitindo sinal de interrupção para o ReAct Engine.
  - Barra de status inferior Rich integrada ao layout do `prompt_toolkit`.
- [ ] Testes unitários do completer e do parser de menções `@`.

### 🚫 Fora de Escopo (Out of Scope / Anti-Metas)
- Não implementar a execução dos 20 Slash Commands (escopo da Sprint 3).
- Não renderizar streaming contínuo via `Rich.Live` (escopo da Sprint 3).
- Não criar clientes MCP (escopo da Sprint 4).

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/tui/
├── completer.py                       # OrionCompleter (suporte a / e @)
├── prompt.py                          # PromptSession assíncrona do prompt_toolkit
└── keybindings.py                     # Atalhos de teclado (Ctrl+C, Alt+Enter, Ctrl+L)
tests/
└── unit/
    ├── test_completer.py              # Testes do autocomplete de comandos e caminhos
    └── test_prompt_session.py         # Testes de histórico e sinais
```

---

## 6. Contratos de Código & Tipagem

```python
from typing import Iterable
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

class OrionCompleter(Completer):
    def get_completions(self, document: Document, complete_event) -> Iterable[Completion]:
        """
        Retorna sugestões dinâmicas:
        - Se o texto sob o cursor começar com '/', retorna comandos com metadados.
        - Se o texto sob o cursor começar com '@', retorna arquivos do workspace.
        """
        ...
```

---

## 7. Estratégia de Implementação (Passo a Passo)

1. **Passo 1:** Configurar dependência `prompt-toolkit` no `pyproject.toml`.
2. **Passo 2:** Desenvolver `OrionCompleter` tratando alternância de contexto (`/` vs `@`).
3. **Passo 3:** Implementar a lógica de varredura rápida de arquivos no workspace com cache em memória para arquivos ignorados.
4. **Passo 4:** Criar `InteractivePrompt` com `PromptSession` assíncrona e keybindings customizados.
5. **Passo 5:** Conectar a barra de status inferior Rich como componente de rodapé dinâmico do `prompt_toolkit`.
6. **Passo 6:** Escrever testes cobrindo completamento de comandos e resolução de menções de arquivo.

---

## 8. Testes Automatizados & Critérios de Aceite (DoD)

### Cenários de Teste Obrigatórios
- **Teste 1:** Digitar `/co` sugere `/compact`, `/context` e `/cost` com suas respectivas descrições.
- **Teste 2:** Digitar `@src/` sugere subdiretórios e arquivos existentes em `src/`, sem listar arquivos de `.git/` ou `node_modules/`.
- **Teste 3:** Envio de `Ctrl+C` durante execução de tarefa emite `TurnCancelledEvent` sem fechar o CLI.

### Definition of Done (DoD)
- [ ] `prompt_toolkit` totalmente integrado com histórico persistente.
- [ ] Autocomplete duplo (`/` e `@`) operacional e veloz.
- [ ] `pytest tests/unit/test_completer.py tests/unit/test_prompt_session.py` passando com 100% de sucesso.
- [ ] Cobertura de testes dos módulos $\ge 90\%$.
- [ ] Documentação de progresso atualizada em `.claudex/progress.md`.
