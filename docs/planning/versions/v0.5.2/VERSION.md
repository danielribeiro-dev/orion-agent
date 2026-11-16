# Spec — v0.5.2 Bridge (Tela cheia, movimento do agente e instalação sem venv)

> **Status:** 🔄 Sprints 0 a 4 implementadas (15–16/11/2026); falta a rodada com modelo real (CA-12) e a validação do Senhor em terminal gráfico  
> **Criada em:** 2026-11-15  
> **Concluída em:** —  
> **Autor(es):** Daniel Dev & Claude (Pair Programming)  
> **Branch:** `feat/v0.5.2-bridge` (criada de `feat/v0.5.1-sprint-1`)  
> **Desvio registrado:** o `CLAUDE.md` pede uma sprint por sessão; o Senhor ordenou executar as cinco em sequência nesta sessão. Cada sprint mantém escopo, testes e commit próprios.

---

## 1. Visão Geral & Motivação

### 1.1 Objetivo
Levar a TUI do ORION ao padrão de um agente de terminal sério: **tela cheia** com o input sempre vivo, pensamento e ferramentas que se movem e se recolhem no lugar, memória legível, e um comando `orion` que funciona sem ativar a venv, com atualização e reversão.

### 1.2 Por que agora?
A rodada de 15/11/2026 (`tui-mcp` + provider roteirizado, custo zero) mostrou que os defeitos mais graves da interface são **limites do modo inline** (prompt entre turnos + `Rich.Live` transiente), não bugs pontuais: a tela "pula" depois do turno, o input some durante o turno, Alt+R reimprime o raciocínio no fim do histórico, o redimensionamento não refaz a quebra das linhas. O Claude Code chegou à mesma conclusão e tornou o modo fullscreen o padrão em 2026. Catálogo completo: `achados-bridge.md` (N-01 a N-24 e A-01 a A-09).

### 1.3 O que NÃO é escopo (anti-metas)
- Voz, aba flutuante e desktop (v0.6.0/v0.7.0).
- Mudar paleta, bloco Stellar ou tokens da Horizon (ADR-039), exceto os glifos `▸`/`▾` (ADR-045).
- Mudanças em `core/`, PEP ou memória além do necessário para a interface.
- Publicar pacote no PyPI ou assinar binários: a atualização usa tags do repositório git.
- Chamada a provedor pago ou free em teste automático.

---

## 2. Decisões Arquiteturais & Diretrizes de Design

### 2.1 Padrões e Invariantes Aplicáveis
- Brain/Body: `orion.core` continua sem I/O; a tela fala só com o `SessionSink` (ADR-032).
- PEP inalterado: o overlay de autorização substitui só a moldura; a decisão continua em `governance/pep.py`; o step-up nuclear segue no popup do SO.
- Sem emojis; glifos da tabela oficial mais `▸ ▾` (ADR-045).
- Ocioso = 0 quadros e 0 tokens.
- Doc-First, cobertura global >= 85%, ruff e mypy strict, `asyncio`.

### 2.2 ADRs desta versão
- **ADR-043:** renderizador fullscreen como padrão, modo clássico como alternativa e reserva automática.
- **ADR-044:** layout de instalação (`~/.local/share/orion`), atalho em `~/.local/bin`, `orion update` e `--rollback`.
- **ADR-045:** linguagem de movimento e orçamento de quadros; glifos `▸ ▾`.

### 2.3 Dependências e Relações
- **Depende de:** v0.5.1 (tokens Horizon, harness `tests/lab/`).
- **Desbloqueia:** v0.5.3 (Memória Viva e Núcleo Enxuto) e v0.6.0 (os estados de pensamento e ferramenta viram falas).

---

## 3. Divisão em Sprints & Entregáveis

| Sprint | Nome | Objetivo | Documento | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Sprint 0** | Spec | Achados, auditoria dos comandos, ADR-043 a 045, design system e telas de referência | [`sprint-0.md`](sprints/sprint-0.md) | ✅ |
| **Sprint 1** | Instalação | `scripts/install.sh`, `orion update`/`--rollback`, `/doctor` | [`sprint-1.md`](sprints/sprint-1.md) | ✅ |
| **Sprint 2** | Casco fullscreen | `ScreenRenderer`, app em tela cheia, input vivo com fila, rolagem, reflow, `/tui`, reserva | [`sprint-2.md`](sprints/sprint-2.md) | ✅ |
| **Sprint 3** | Movimento | Pensamento, ferramentas, rodapé de turno, transcrição, sinais do terminal, PT-BR | [`sprint-3.md`](sprints/sprint-3.md) | ✅ |
| **Sprint 4** | Memória e comandos | `/timeline`, `/recall`, `/memory` legíveis e correções da auditoria | [`sprint-4.md`](sprints/sprint-4.md) | ✅ |

---

## 4. Arquitetura Alvo & Componentes Afetados

```
scripts/install.sh                         [novo]  Sprint 1
src/orion/install.py                       [novo]  versões, symlink atômico, update/rollback
src/orion/tui/screen/transcript.py         [novo]  modelo de células com estado recolhido
src/orion/tui/screen/console.py            [novo]  Console Rich que grava células (comandos e modais)
src/orion/tui/screen/renderer.py           [novo]  ScreenRenderer: o StreamRenderer sem Rich.Live
src/orion/tui/screen/app.py                [novo]  Application em tela cheia, fila, rolagem, overlays
src/orion/tui/screen/terminal.py           [novo]  synchronized output, título, progresso, foco
src/orion/tui/modal.py                     [mod]   delega ao host da tela cheia quando ativo
src/orion/tui/stream_renderer.py           [mod]   estados do pensamento, grupos, rodapé de turno
src/orion/tui/status_bar.py                [mod]   PT-BR, prioridade do PEP e do modo
src/orion/tui/commands/{memory,...}.py     [mod]   listas legíveis, correções A-01..A-09
src/orion/cli.py                           [mod]   escolha do renderizador, update, resumo na saída
```

---

## 5. Matriz de Critérios de Aceite da Versão (DoD Global)

| ID | Cenário | Comportamento Esperado | Como Validar | Status |
|:---|:---|:---|:---|:---|
| CA-01 | `orion` sem venv | Num HOME limpo, `scripts/install.sh` deixa `orion` no PATH | `pytest tests/unit/test_install.py` + execução manual | ✅ |
| CA-02 | Atualizar e reverter | `orion update` instala a tag nova ao lado e troca o symlink; `--rollback` volta | `tests/unit/test_install.py` | ✅ |
| CA-03 | Input vivo | O input aparece e aceita texto durante pensamento, texto e ferramenta; Enter enfileira | `pytest -m lab tests/lab/scenarios/test_fullscreen.py` | ✅ |
| CA-04 | Expandir no lugar | Alt+R abre e fecha o raciocínio na mesma posição da transcrição | `tests/unit/test_screen_transcript.py` + lab | ✅ |
| CA-05 | Reflow | 110 → 80 colunas refaz a quebra; status line mantém modo e PEP | lab | ✅ |
| CA-06 | Ocioso | Nenhuma escrita no pty em 3 s sem atividade | lab | ✅ |
| CA-07 | Reserva | `ORION_TUI=classic`, `TERM=dumb` e duas partidas falhas caem no modo clássico | `tests/unit/test_screen_app.py` | ✅ |
| CA-08 | Saída | Ao sair, a tela é restaurada e o resumo com `--resume <id>` fica no scrollback | lab | ✅ |
| CA-09 | Pensamento | Linha viva com tempo e tokens; bloco recolhido `▸`; raciocínio curto absorvido | `tests/unit/test_stream_motion.py` | ✅ |
| CA-10 | Memória | `/timeline` e `/recall` sem markdown cru, uma linha por evento, papéis em PT-BR | `tests/unit/test_memory_views.py` | ✅ |
| CA-11 | Sem regressão | Suíte padrão e lab da v0.5.1 passam no modo clássico | `pytest tests/` + `pytest -m lab` | ✅ |
| CA-12 | Rodada real | Turno com modelo real em tela cheia, sem artefatos | manual, `ORION_LIVE=1`, <= 15 req | ⏳ |

---

## 6. Checklist de Conclusão da Spec (Congelamento)

- [x] Achados e auditoria registrados (`achados-bridge.md`).
- [x] ADR-043, 044 e 045 registrados em `.claudex/decisions.md` (aprovados pelo Senhor ao aprovar o plano em 15/11/2026).
- [x] `CLI_DESIGN_SYSTEM.md` §8 e `CLI_AGENT_RULES.md` atualizados.
- [ ] Todos os critérios de aceite validados.
- [ ] Cobertura >= 85%, `ruff` e `mypy` limpos.
- [ ] Um commit por sprint; merge e tag só com confirmação do Senhor.

---

## 7. Riscos e Pendências Conhecidas

| Risco | Mitigação |
|:---|:---|
| Tela alternativa esconde a conversa da busca do terminal | Ctrl+O + `[` despeja a transcrição no scrollback; resumo ao sair; modo clássico disponível |
| Captura do mouse impede a seleção nativa | Shift+arrastar seleciona; `ORION_MOUSE=0` desliga a captura |
| Terminais que ignoram synchronized output ou o tratam mal | `ORION_SYNC_OUTPUT=0`; desligado em `TERM=linux` |
| `pyte` sem suporte completo à tela alternativa | O lab lê o quadro final; validação visual pelo `tui-mcp` |
| Partida falha em terminal exótico | Contador de partidas falhas em `~/.orion/tui_state.json`; duas falhas = modo clássico |
| Atualização é cadeia de suprimento | Só tags do repositório configurado; aplicar exige confirmação explícita no terminal |
