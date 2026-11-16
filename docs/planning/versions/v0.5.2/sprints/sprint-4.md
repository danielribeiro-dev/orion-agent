# Sprint — v0.5.2 Sprint 4: Memória e comandos

> **Status:** ⏳ · **Achados:** N-18 a N-21, A-01 a A-09 · **CA:** CA-10

## Escopo
1. `tui/memory_views.py`: resumo de markdown em texto plano, papéis em PT-BR, agrupamento por dia, linha única com reticências.
2. `/timeline [N]` e `/recall <termo>` com o padrão (fatos com selo de status; eventos com termo destacado).
3. `/memory`: nomes humanos das esferas; nome do perfil vindo de `~/.orion` (não do usuário do SO).
4. Correções da auditoria A-01 a A-07.

## Testes
`tests/unit/test_memory_views.py` e ajustes nos testes de comandos.
