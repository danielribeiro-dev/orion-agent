# Horizon — telas de referência (v0.5.1)

Cinco telas em **texto puro**, 1 caractere = 1 célula, geradas da proposta aprovada em 11/11/2026. São a referência para o teste golden da Sprint 2 (comparar estrutura e texto; as cores seguem a tabela de tokens em `CLI_DESIGN_SYSTEM.md` §7).

| Arquivo | Largura | Mostra |
|:---|:---:|:---|
| `splash-110.txt` | 110 | Banner lateral compacto, dica, prompt e status line |
| `splash-80.txt` | 80 | Variante estreita: texto desce para baixo do logo |
| `autocomplete-110.txt` | 110 | Menu com seleção, categorias e rodapé de atalhos |
| `stream-110.txt` | 110 | Raciocínio, ferramentas com resultado `›`, diff, saída colapsada, spinner |
| `pep-110.txt` | 110 | Autorização PEP com moldura âmbar e teclas |

## Ressalvas (leia antes de implementar)

1. **Versão e dados são exemplos.** `v0.5.0`, `24% ctx`, `$0.088` e nomes de modelo vêm de `__version__`, da sessão e do ledger.
2. **Durante um turno** o ORION hoje não mantém o prompt ativo: mostra spinner e status line. As telas `stream-110.txt` e `pep-110.txt` desenham o bloco do prompt sob o spinner, que é o **estado alvo** só se o spike do V-11 (input durante o turno) for aprovado. Sem ele, o bloco do prompt fica ausente nessas duas telas e permanece a status line (ver `sprints/sprint-1.md` §4, tarefa 1B.3).
3. A sonda que gerou as telas usava o `−` tipográfico (U+2212) no diff. É o único glifo fora da tabela oficial; ver ADR-039.
4. Os underscores de `stream_renderer.py` somem em alguns emuladores de teste por corte de linha; não é problema do ORION.
5. O mock correspondente no Figma (página "Proposta Horizon") **não foi criado**: o plano Starter atingiu o limite de chamadas do MCP. Quando houver cota, enviar a grade destas telas; até lá estes arquivos são a referência.
