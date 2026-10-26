# O.R.I.O.N — Active Context (Memória de Sessão de Desenvolvimento)

> **Data de Atualização:** 26/10/2026  
> **Status Atual:** v0.4.0 Sprint 2 CONCLUÍDA (928 testes passando, 100% sucesso, Cobertura TUI 95.69%).  
> **Fase Ativa:** v0.4.0 (High-Performance Stream CLI, Slash Commands & Native MCP).  
> **Branch Ativo:** `version/v0.4.0`  
> **Regra Suprema:** Nenhuma linha de código em `src/` é escrita sem o comando explícito de início da Sprint correspondente (Doc-First).

---

## 🎯 Foco Imediato & Estado da v0.4.0 (Stream CLI & Native MCP)
1. **Branch de Trabalho:** `version/v0.4.0`
2. **Entregas da Sprint 2:**
   - Dependência oficial `prompt-toolkit>=3.0.40` adicionada ao `pyproject.toml`.
   - `OrionCompleter` em `src/orion/tui/completer.py` unificando autocompletar flutuante:
     - `SlashCommandCompleter`: detecta prefixo `/` e sugere os 22 comandos cadastrados com descrições curtas e ícones.
     - `PathMentionCompleter`: detecta prefixo `@` e sugere arquivos e diretórios a partir da raiz do workspace ativo, ignorando `.git/`, `__pycache__/`, `node_modules/` e padrões de `.gitignore`.
     - `GitIgnoreMatcher`: parsing de regras `.gitignore` e verificação rápida de caminhos ignorados com cache em memória.
     - `parse_mentions` e `resolve_mentions`: extração segura de menções `@` e resolução validada contra ataques de directory traversal (`../`).
   - `create_key_bindings` em `src/orion/tui/keybindings.py`:
     - Atalho `Ctrl+C` capturado graciosamente (limpa buffer ou emite cancelamento).
     - Atalho `Alt+Enter` (`Escape, Enter`) para suporte a entrada multilinha.
     - Atalho `Ctrl+L` para limpeza do terminal preservando o buffer.
   - `InteractivePrompt` em `src/orion/tui/prompt.py`:
     - Histórico persistente gravado em `~/.orion/history` com fallback para `InMemoryHistory`.
     - Barra de status inferior Rich integrada ao layout do `prompt_toolkit`.
     - Execução de tarefas com captura graciosa de `KeyboardInterrupt` (`Ctrl+C`) e emissão de `TurnCancelledEvent` para o `EventBus` sem derrubar o CLI.
   - `TurnCancelledEvent` adicionado a `src/orion/core/events.py`.
   - 41 novos testes unitários adicionados em `tests/unit/test_completer.py` e `tests/unit/test_prompt_session.py` (928 testes globais passando, 0 regressões).
3. **Métricas de Qualidade Atuais:**
   - Total de Testes: 928 passando (0 falhas).
   - Cobertura do Pacote TUI: 95.69%.
   - Mypy Strict: 0 erros em 8 arquivos TUI + 1 arquivo core/events.
   - Ruff Lint: 0 avisos / 100% limpo.

---

## 📌 Próximo Passo
Aguardar aprovação do usuário e comando explícito para iniciar a **Sprint 3 (Streaming Vivo, Diffs Cirúrgicos & 20 Slash Commands)** da v0.4.0.
