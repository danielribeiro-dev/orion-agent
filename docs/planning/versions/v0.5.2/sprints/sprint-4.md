# Sprint — v0.5.2 Sprint 4: Memória e comandos

> **Status:** ✅ Implementada em 16/11/2026 · **Achados:** N-18 a N-21, A-01 a A-09 · **CA:** CA-10

## Escopo
1. `tui/memory_views.py`: resumo de markdown em texto plano, papéis em PT-BR, agrupamento por dia, linha única com reticências.
2. `/timeline [N]` e `/recall <termo>` com o padrão (fatos com selo de status; eventos com termo destacado).
3. `/memory`: nomes humanos das esferas; nome do perfil vindo de `~/.orion` (não do usuário do SO).
4. Correções da auditoria A-01 a A-07.

## Testes
`tests/unit/test_memory_views.py` e ajustes nos testes de comandos.

## Registro de implementação (16/11/2026)
- `tui/memory_views.py`: `markdown_to_plain`, papéis (`Senhor`, `ORION`, `ferramenta`, `sistema`), dias (`hoje`, `ontem`, `dd/mm`), `TimelineView` e `FactsView` (uma linha por item, reticências na largura atual, termo destacado).
- `/timeline` e `/recall` usam as visões; `/memory` com nomes humanos e perfil lido de `~/.orion/profile.json` (padrão `Senhor`; o `UserProfile` não era carregado em lugar nenhum, por isso aparecia o usuário do git/SO).
- Auditoria: A-01 `/learn` e `/grill-me` sem conversa não gastam turno; A-02 voz na v0.6.0; A-03 `/merge` em PT-BR; A-04 `/context` com vírgula e `1M`; A-05 `/cost` em `US$` com vírgula e milhar com ponto; A-06 categorias e descrições do `/help` em PT-BR; A-07 `/daemon` legível.
- **Desvio:** A-01 foi corrigido de outra forma: em vez de exigir argumento (o `/learn` sem nome é uso legítimo), o comando recusa quando não há conversa a usar.
- **Causa de N-19:** irrelevante após a troca; as visões cortam cada linha explicitamente com `Text.truncate`.
- Bug achado nos testes e corrigido: `end=""` nas linhas juntava a lista numa linha só.
- Testes: `test_memory_views.py` (10). Cobertura global 93,6%.
