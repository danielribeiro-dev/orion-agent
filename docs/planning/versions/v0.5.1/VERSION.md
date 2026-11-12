# Spec — v0.5.1 Horizon (Identidade Visual e Estabilidade da TUI)

> **Status:** 🔄 Em Execução — spec congelada e aprovada pelo Senhor em 11/11/2026; Sprint 1 iniciada  
> **Criada em:** 2026-11-11  
> **Concluída em:** —  
> **Autor(es):** Daniel Dev & Claude (Pair Programming)  
> **Branch:** `feat/v0.5.1-sprint-1` (criada de `feat/v0.5.0-sprint-7`; `version/v0.5.1` nasce da `main` quando a v0.5.0 for mergeada)  

---

## 1. Visão Geral & Motivação

### 1.1 Objetivo
Entregar a identidade visual **Horizon** e, no mesmo pacote, eliminar os bugs de TUI que só aparecem em movimento. A interface nova não pode herdar os defeitos da antiga: cada achado V-01 a V-17 (`achados-tui.md`) tem sprint, critério de aceite e teste de regressão.

### 1.2 Por que agora?
A rodada manual de 09/11 empurrou toda a interface para esta versão (`rascunho-achados-teste-manual.md`). Em 11/11, a análise visual contra Claude Code e Hermes e os testes dinâmicos com provider roteirizado mostraram dois problemas distintos: aparência (banner, menu, réguas, PEP) e comportamento (download de 67 MB no primeiro envio, texto perdido ao cancelar, tempo de ferramenta inflado, menu que não fecha). Corrigir só a aparência esconderia o comportamento atrás de uma tela bonita.

### 1.3 O que NÃO é escopo (anti-metas)
- Desktop/eDEX (v0.7.0), voz e aba flutuante (v0.6.0/v0.7.0).
- Tema claro e skins carregáveis por YAML (como no Hermes): registrados como ideia, não entram.
- Mudar paleta Deep Cosmos, bloco Stellar ou glifos aprovados, além do que o ADR-039 lista.
- Qualquer mudança em `core/`, PEP ou memória além do mínimo para os bugs V-09, V-12 e V-17.
- Chamada a provedor pago em teste automático. A rodada com modelo real segue o `ORION_LIVE=1` e o teto de 15 das 50 req/dia do OpenRouter free.

---

## 2. Decisões Arquiteturais & Diretrizes de Design

### 2.1 Padrões e Invariantes Aplicáveis
- Brain/Body: `orion.core` não faz I/O direto. O progresso de download vai pelo sink, nunca por `print` ou tqdm.
- Sem emojis; glifos da tabela oficial (`CLI_DESIGN_SYSTEM.md` §1.2) mais o `−` do diff (ADR-039).
- Toda cor sai de `ORION_COLORS`; os três tokens novos entram **antes** do código (este documento e `CLI_DESIGN_SYSTEM.md` §7).
- Regra 2 de `CLI_AGENT_RULES.md` permanece: nenhum fundo sólido na largura total da linha de status.
- Regra 3 (duas réguas dentro do `HSplit`) permanece; só a cor muda, de `text_primary` para `rule`.
- Doc-First, cobertura global >= 85%, ruff e mypy strict, `asyncio`.

### 2.2 ADRs desta versão (aprovados em 11/11/2026)
- **ADR-039:** identidade visual Horizon (tokens `rule`, `faint`, `sel`; banner lateral; sem dock; menu e PEP; glifo `−`).
- **ADR-040:** a TUI não depende de CPR nem de rede (rodapé sem CPR; modelo de embeddings só com consentimento; progresso pelo sink).
- **ADR-041:** harness de TUI em `tests/lab/` (pty + pyte, provider roteirizado, sondas de cadência), promovendo a sonda desta análise; complementa o ADR-038.

### 2.3 Dependências e Relações
- **Depende de:** v0.5.0 fechada (merge e tag exigem autorização do Senhor). A Sprint 1 pode começar sobre `feat/v0.5.0-sprint-7` se o Senhor preferir antecipar.
- **Desbloqueia:** v0.6.0 e a aba flutuante (mesmos tokens), e o desktop v0.7.0 (os mesmos tokens alimentam o Figma).

---

## 3. Divisão em Sprints & Entregáveis

| Sprint | Nome da Sprint | Objetivo Principal | Documento | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Sprint 1** | Harness e Bugs Dinâmicos | `tests/lab/` com provider roteirizado; corrigir V-05, V-06, V-09 a V-17 antes de mexer no visual | [`sprint-1.md`](sprints/sprint-1.md) | 🔄 Em execução |
| **Sprint 2** | Horizon Visual | Tokens, banner, prompt, menu, ferramentas, diff, PEP, status line, larguras, fallback de cor; V-01 a V-04, V-07, V-08 | [`sprint-2.md`](sprints/sprint-2.md) | 📋 Planejando |

Ordem deliberada: **primeiro os testes e os bugs, depois a pintura**. A Sprint 2 usa o harness da Sprint 1 como rede de segurança.

---

## 4. Arquitetura Alvo & Componentes Afetados

```
tests/lab/{pty_driver,scripted_provider,probes}.py   [novo] Sprint 1
tests/lab/scenarios/                                 [novo] cenários de cadência, cancelamento, menu, PEP
src/orion/tui/theme.py                               [mod]  tokens rule, faint, sel (Sprint 2)
src/orion/tui/{banner,status_bar}.py                 [mod]  banner lateral, dica por largura, status line
src/orion/tui/prompt.py                              [mod]  sem dock_to_bottom, menu com seleção, rodapé de atalhos
src/orion/tui/completer.py                           [mod]  ordem por categoria, categoria na linha
src/orion/tui/keybindings.py                         [mod]  Esc fecha menu, alias Alt+E, aviso de Ctrl+C
src/orion/tui/stream_renderer.py                     [mod]  commit de código fechado, cauda no cancelamento, cronômetro, linha ›
src/orion/tui/{panels,diff_viewer}.py                [mod]  PEP âmbar com decisão, diff com moldura rule
src/orion/tui/session.py                             [mod]  aviso de 5 s sem token, status durante modal
src/orion/memory/vector_store.py                     [mod]  só modelo em cache; progresso pelo sink (V-09)
docs/design/{CLI_DESIGN_SYSTEM,CLI_AGENT_RULES}.md   [mod]  esta entrega (spec)
docs/design/horizon/*.txt                            [novo] telas de referência
```

---

## 5. Matriz de Critérios de Aceite da Versão (DoD Global)

| ID | Cenário | Comportamento Esperado | Como Validar | Status |
|:---|:---|:---|:---|:---|
| CA-01 | Primeiro envio sem rede | Nenhum acesso à rede, nenhuma barra de progresso; recall cai no BM25 e avisa uma vez | `pytest -m lab tests/lab/scenarios/test_first_turn_offline.py` | ⏳ |
| CA-02 | Resposta longa | 10 a 12 atualizações/s, pausa <= 300 ms após o primeiro token, CPU <= baseline × 1,2, sem quadro duplicado | `pytest -m lab tests/lab/scenarios/test_stream_cadence.py` | ⏳ |
| CA-03 | Cancelar com Ctrl+C | O texto já visível permanece no histórico; mensagem de interrupção; prompt volta limpo | `pytest -m lab tests/lab/scenarios/test_cancel_keeps_text.py` | ⏳ |
| CA-04 | Tempo de ferramenta | Não inclui a espera da aprovação | `pytest tests/unit/test_stream_renderer.py` | ⏳ |
| CA-05 | Modal PEP | Decisão registrada sob o modal; status line visível; nível igual ao do PEP | `pytest -m lab tests/lab/scenarios/test_pep_modal.py` | ⏳ |
| CA-06 | Menu de comandos | Esc fecha; seleção com fundo; ordem por categoria; rodapé de atalhos; sem resíduo após Ctrl+C | `pytest -m lab tests/lab/scenarios/test_menu.py` | ⏳ |
| CA-07 | Banner e larguras | 110, 80 e 60 colunas sem corte; dica cabe; sem vão entre banner e prompt | `pytest -m lab tests/lab/scenarios/test_layout_widths.py` + golden em `docs/design/horizon/` | ⏳ |
| CA-08 | Rodapé sem CPR | Status line aparece mesmo com terminal que não responde CPR | `pytest -m lab tests/lab/scenarios/test_footer_no_cpr.py` | ⏳ |
| CA-09 | Tokens e glifos | Só cores de `ORION_COLORS`; nenhum emoji novo; `−` só no diff | `pytest tests/unit/test_theme.py` + `grep` do checklist de `CLI_AGENT_RULES.md` §4 | ⏳ |
| CA-10 | Degradação de cor | Sem truecolor, mapeia para 256 cores; `NO_COLOR` respeitado; hierarquia legível | `pytest tests/unit/test_theme.py` | ⏳ |
| CA-11 | Sem regressão | Suíte da v0.5.0 passa; réguas F-07/F-08 sem linhas fantasma | `pytest tests/` + cenários do lab | ⏳ |
| CA-12 | Rodada com modelo real | Um turno de cada tipo com o OpenRouter free, sem artefatos; <= 15 req | roteiro manual com `ORION_LIVE=1` | ⏳ |

---

## 6. Checklist de Conclusão da Spec (Congelamento)

- [x] ADR-039, 040 e 041 aprovados pelo Senhor (11/11/2026).
- [x] `CLI_DESIGN_SYSTEM.md` e `CLI_AGENT_RULES.md` revisados e aprovados.
- [ ] Todos os critérios de aceite validados.
- [ ] Testes com cobertura >= 85% e zero regressões; `ruff` e `mypy` limpos.
- [ ] `.claudex/progress.md`, `active_context.md` e a tabela de sprints atualizados.
- [ ] Um commit por sprint (`feat(tui): v0.5.1 Sprint N — <título>`); merge e tag só com confirmação do Senhor.

---

## 7. Riscos e Pendências Conhecidas

| Risco | Mitigação |
|:---|:---|
| Remover o dock muda a posição do prompt em `/clear` e ao redimensionar | Cenários do lab em 3 larguras; validar `/clear` e resize |
| Input durante o turno (V-11) pode quebrar a regra 3 (linhas fantasma) | Spike com prova em pty antes de adotar; plano B sem eco |
| Reflow do histórico só é real num terminal gráfico | Validação manual em Ghostty, Kitty e GNOME Terminal pelo Senhor |
| Figma Horizon ausente (cota do MCP) | `docs/design/horizon/*.txt` é a referência; enviar ao Figma quando houver cota |
| Hipóteses H de V-10 e V-17 | Primeira tarefa de cada uma é reproduzir em teste vermelho |
