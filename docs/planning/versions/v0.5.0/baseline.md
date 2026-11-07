# Baseline — v0.5.0 Sprint 0 (2026-11-06)

## Suíte automatizada (branch `version/v0.5.0`, sobre `ded03f4`)
- `pytest tests/`: **1119 passed**, 0 falhas, ~17 s (617 warnings, entre eles `datetime.utcnow()` em `memory/file_syncer.py:137`).
- Cobertura global: **93,70%** (limite do projeto: 85%). Menor cobertura relevante: `tui/modal.py` 83% (exige TTY).
- Slash commands no catálogo (`OFFICIAL_SLASH_COMMANDS`): **23**.
- Versão: `orion --version` → `ORION v0.4.0-alpha`.

## Turno com provedor real: NÃO executado
Motivo: o ambiente não tem `OPENROUTER_API_KEY` nem `ANTHROPIC_API_KEY`, e o Ollama não está instalado. `~/.orion/config.json` aponta para `qwen2.5-coder:1.5b` (Ollama local), que não está disponível. Nenhuma chamada paga foi feita.

Consequência: a lacuna "nenhum turno real validado" da v0.4.0 permanece aberta. Ela passa a ser coberta pela Sprint 1 (teste `ORION_LIVE=1` com a chave Anthropic). Ao iniciar a Sprint 1, medir antes de mexer no núcleo: 1 turno simples, 1 com `read_file`, 1 com `edit_file`, registrando tokens, custo e falhas.

## Bugs/dívidas observados (sem correção nesta sprint)
- Protocolo `<tool_call>` em texto: 1 tool por resposta, JSON inválido vira resposta final (alvo da Sprint 2).
- `stream()` sem retry; retry de `complete()` não cobre 5xx apesar da docstring (Sprint 1).
- `HybridRetriever`, `skills_engine`, manifest, `EnvironmentMonitor` e circuit breaker não ligados à `AgentSession` (Sprints 1 e 3).
- Compactação só manual; observações intra-turno sem poda (Sprint 3).
- `_RISK_MAP` em `runtime/local_provider.py` duplica `governance/permissions.py` (Sprint 2).
- Início do `orion-agent` ~0,4 s (meta CA-01 da v0.4.0: < 100 ms).
- `~/.orion` contém arquivos órfãos de outra versão (`sessions.db`, `memory.db`, `chats/`, `automations.json`); tratar na Sprint 8.

## Pendências de release (exigem autorização do Senhor)
Merge de `version/v0.4.0` em `main` e tags `v0.3.0`/`v0.4.0`.
