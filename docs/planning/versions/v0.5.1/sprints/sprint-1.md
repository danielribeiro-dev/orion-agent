# Sprint — v0.5.1 Sprint 1: Harness e Bugs Dinâmicos

> **Status:** 🔄 Em execução (comando de início do Senhor em 11/11/2026, na mesma sessão da spec)  
> **Versão Relacionada:** v0.5.1  
> **Responsável / Agente:** Daniel Dev & Claude (via ORION)  
> **Data de Início:** 11/11/2026  
> **Data de Conclusão:** —  
> **ADRs:** 040, 041 · **Achados:** V-05, V-06, V-09 a V-17 (`../achados-tui.md`)

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Criar a rede de segurança de TUI em movimento (`tests/lab/`) e corrigir, com teste vermelho antes, os bugs de comportamento. Nenhuma mudança visual nesta sprint.
* **Dependências Prévias:** v0.5.0 estável. ADR-038 (MCPs de TUI) vigente.
* **Entregável Verificável:** `pytest -m lab` roda os cenários com provider roteirizado, sem rede e sem custo; cada um dos 11 achados tem cenário que falha antes e passa depois.

---

## 2. Contexto de Engenharia

* **Por que existe:** os testes atuais usam `Console(file=StringIO)` e não enxergam cadência, cancelamento, teclas, menu nem rodapé. Os bugs V-09 a V-17 só aparecem em movimento. A sonda criada em 11/11/2026 (pty + pyte, amostragem de 20 ms, provider com streaming a ~200 car/s) os reproduziu e vira a base do harness.
* **Fundamentos:** ADR-038 (`tui-mcp` olha, `ptywright` regride) e `scripts/dogfood/` (ponte com o Claude Code, sem cadência real). Esta sprint não os substitui: o lab cobre cadência e regressão automática; o dogfood segue para validar o modelo-ponte.
* **Ponto de partida do código:** `../referencia/lab/` (provider roteirizado e sonda pty+pyte, já funcionais) e `../referencia/horizon/` (grade das telas). Ver `../referencia/README.md`.
* **Decisões novas:** ADR-040 (TUI sem CPR e sem rede) e ADR-041 (harness `tests/lab/`).

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Antes | Depois |
| :--- | :--- | :--- |
| **Teste de TUI** | `StringIO`, sem cor, tempo ou teclas | Pty real com emulador (pyte), CPR respondido, amostragem e métricas |
| **Provider em teste** | Ponte manual ou fake instantâneo | `ScriptedProvider` com cadência configurável, pausas e erros |
| **Primeiro envio** | Baixa 67 MB e suja a tela | Zero rede; BM25 até haver modelo em cache; instalação com consentimento |
| **Cancelar (Ctrl+C)** | Cauda da resposta se perde (indício) | Cauda gravada no histórico |
| **Tempo de ferramenta** | Inclui espera de aprovação | Só a execução |
| **Esc no menu** | Sem efeito | Fecha o menu |
| **Rodapé** | Depende de CPR | Independe |

---

## 4. Escopo da Sprint

### ✅ No Escopo
- [ ] **1A.1 — `tests/lab/pty_driver.py`:** sobe o ORION num pty com `HOME` temporário e `HF_HUB_OFFLINE=1`; emulador `pyte`; **responde CPR** (`ESC[6n`); `send`, `key`, `resize`, `wait_for`, amostragem a 20 ms; devolve tela, histórico e linha do tempo de hashes.
- [ ] **1A.2 — `tests/lab/scripted_provider.py`:** provider com cadência (`chunk`, `delay`), raciocínio, pausa no meio do stream, erro, tool_use em estágios e cenários nomeados (curto, longo, código, pensar, travar, ferramentas, erro). Chave de API falsa que nunca sai da máquina.
- [ ] **1A.3 — `tests/lab/probes.py` e baseline:** métricas (primeiro caractere, duração, atualizações/s, maior pausa, CPU via `/proc`). Baseline gravado em `tests/lab/baseline.json` com a máquina e o commit; gates relativos (ver CA-02).
- [ ] **1A.4 — Perfil de CPU:** reproduzir os ~20% de núcleo durante o stream, localizar o custo (re-render do Markdown inteiro a 12 Hz) e propor redução sem perder fluidez. Entregar medição antes e depois; se a redução exigir mudar a cadência, registrar em nota do ADR-039.
- [ ] **1A.5 — Marcador `lab`:** `@pytest.mark.lab`, opt-in (`pytest -m lab`), fora da suíte padrão de ~20 s. `pyte` entra no extra `dev`. Documentar em `.claudex/tooling.md` §1.
- [ ] **1B.1 — V-09 (rede e download):** `vector_store` passa a usar só modelo em cache (`local_files_only`); sem cache, cai no BM25 e o recall avisa **uma vez** por sessão. Instalação do modelo por comando explícito do Senhor (consentimento), com progresso pelo sink; `HF_HUB_DISABLE_PROGRESS_BARS` e telemetria desligados. Nenhum tqdm no terminal.
- [ ] **1B.2 — V-10 e V-17 (stream):** (a) reproduzir em teste vermelho; (b) commit de bloco de código apenas fechado; (c) cancelamento grava a cauda do `Live` no histórico antes da mensagem de interrupção.
- [ ] **1B.3 — V-11 (input durante o turno):** **spike** de até meio dia: leitura leve de teclas durante o turno com eco numa linha abaixo do spinner, sem criar janela horizontal extra no prompt (regra 3). Critério de adoção: sem linha fantasma em pty, em 3 larguras. **Plano B**, adotado se o spike falhar: indicador `1 na fila` sem eco. Registrar a escolha no `sprint-1.md` §8.1.
- [ ] **1B.4 — V-12 e V-13 (ferramenta e modal):** cronômetro da ferramenta inicia na execução; a espera de aprovação é medida à parte e não aparece no tempo. Sob o modal PEP, linha de decisão (`✔ aprovado` ou `✖ negado`); a status line continua visível enquanto o modal está aberto. Nível exibido segue o PEP (docs corrigidas).
- [ ] **1B.5 — V-14, V-15, V-16 (teclas e menu):** Esc com menu aberto chama `cancel_completion()`; Alt+E expande **com cabeçalho** (`✔ Bash: ... · saída completa`); alias para Alt+Shift+E; Ctrl+C com menu limpa sem resíduo e mostra `Ctrl+C de novo para sair` por 2 s.
- [ ] **1B.6 — V-05 e V-06 (CPR):** rodapé independente de CPR (ADR-040); suprimir o aviso do prompt_toolkit quando o terminal não responde; tabela de terminais suportados em `CLI_DESIGN_SYSTEM.md`.
- [ ] **1B.7 — Aviso de travamento:** após 5 s sem token com o turno ativo, linha discreta `sem resposta há 5s · Ctrl+C cancela` (o spinner já indica vida, não indica espera anormal).

### 🚫 Fora de Escopo
- Qualquer cor, layout, glifo ou texto novo de identidade (Sprint 2). Mensagens novas desta sprint usam os tokens e glifos atuais.
- Modelo real em teste automático. A rodada com o OpenRouter free (<= 15 req) é manual, com `ORION_LIVE=1`, ao final.
- Substituir `scripts/dogfood/` ou o `ptywright`.

---

## 5. Arquitetura & Arquivos Afetados

```
tests/lab/{__init__,pty_driver,scripted_provider,probes}.py    [novo]
tests/lab/scenarios/test_{first_turn_offline,stream_cadence,cancel_keeps_text,pep_modal,menu,footer_no_cpr}.py [novo]
tests/lab/baseline.json                                        [novo]
tests/unit/test_stream_renderer.py                             [mod] cronômetro, cerca aberta, cauda
src/orion/memory/vector_store.py                               [mod] local_files_only, aviso único, instalação explícita
src/orion/tui/{stream_renderer,keybindings,prompt,panels,session}.py [mod]
src/orion/tui/commands/memory.py (ou doctor)                   [mod] comando de instalar modelo, com consentimento
pyproject.toml                                                 [mod] extra dev com pyte; marcador lab
.claudex/tooling.md                                            [mod] seção do harness `tests/lab/`
```

Novo comando ou subcomando segue `CLI_AGENT_RULES.md` §2 (classe em `tui/commands/` + registro em `tui/completer.py`, sem emoji).

---

## 6. Contratos de Código & Tipagem

```python
class ScriptedProvider(BaseLLMProvider):
    """Provider de teste: streaming com cadência. Nunca faz rede."""
    def __init__(self, script: Script, chunk: int = 6, delay: float = 0.03) -> None: ...

class Script(BaseModel):
    text: str = ""
    reasoning: str = ""
    tools: list[tuple[str, dict[str, Any]]] = []   # estágio por resultado de tool
    stall_after: float | None = None               # fração do texto; pausa em segundos
    stall_seconds: float = 0.0
    error: str | None = None

class Probe(BaseModel):                            # métricas de um cenário
    first_char_s: float | None
    total_s: float
    updates_per_s: float
    max_gap_s: float
    cpu_core_pct: float
    final_screen: str
    history: str
```

---

## 7. Estratégia de Implementação

1. 1A inteira primeiro: driver, provider, baseline e um cenário vermelho por achado (**antes** de qualquer correção).
2. 1B em commits pequenos por achado, cada um tornando verde o seu cenário. 1B.3 (spike) por último, com decisão registrada.
3. Rodada manual com o OpenRouter free (<= 15 req), um turno curto, um longo, um com ferramenta; capturas com `tui-mcp`.
4. Commit único da sprint conforme `CLAUDE.md`: `feat(tui): v0.5.1 Sprint 1 — harness e bugs dinâmicos`.

---

## 8. Testes & Critérios de Aceite (DoD)

- Cada achado V-05, V-06, V-09 a V-17 tem cenário que falha antes da correção (guardar a saída do vermelho em §8.1).
- CA-01 a CA-06 e CA-08 da `VERSION.md` verdes. Suíte padrão (`pytest tests/`) sem regressão; cobertura >= 85%; `ruff` e `mypy` limpos.
- Nenhum teste automático toca rede, provedor pago ou o `~/.orion` real (`HOME` e `XDG_RUNTIME_DIR` temporários).
- [ ] `.claudex/progress.md`, `active_context.md`, `tooling.md` e a tabela da `VERSION.md` atualizados.

## 8.1 Registro de implementação

_(preencher ao concluir: commits, decisão do spike V-11, saídas dos testes vermelhos, números antes e depois de CPU e cadência, desvios.)_

---

## 9. Critérios de Parada

1. Qualquer cenário do lab que chame rede, provedor pago ou escreva fora do `HOME` temporário.
2. Correção que reintroduza linha fantasma nas duas réguas do prompt (F-07/F-08).
3. Mudar `core/` ou o PEP além do necessário para V-12/V-13.
4. O spike V-11 consumir mais de meio dia sem prova: adotar o plano B e seguir.
5. Redução de CPU que derrube a cadência abaixo de 10 atualizações por segundo.
