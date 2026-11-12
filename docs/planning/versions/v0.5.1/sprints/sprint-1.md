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
- [x] **1A.1 — `tests/lab/pty_driver.py`:** sobe o ORION num pty com `HOME` temporário e `HF_HUB_OFFLINE=1`; emulador `pyte`; **responde CPR** (`ESC[6n`); `send`, `key`, `resize`, `wait_for`, amostragem a 20 ms; devolve tela, histórico e linha do tempo de hashes.
- [x] **1A.2 — `tests/lab/scripted_provider.py`:** provider com cadência (`chunk`, `delay`), raciocínio, pausa no meio do stream, erro, tool_use em estágios e cenários nomeados (curto, longo, código, pensar, travar, ferramentas, erro). Chave de API falsa que nunca sai da máquina.
- [x] **1A.3 — `tests/lab/probes.py` e baseline:** métricas (primeiro caractere, duração, atualizações/s, maior pausa, CPU via `/proc`). Baseline gravado em `tests/lab/baseline.json` com a máquina e o commit; gates relativos (ver CA-02).
- [x] **1A.4 — Perfil de CPU:** reproduzir os ~20% de núcleo durante o stream, localizar o custo (re-render do Markdown inteiro a 12 Hz) e propor redução sem perder fluidez. Entregar medição antes e depois; se a redução exigir mudar a cadência, registrar em nota do ADR-039.
- [x] **1A.5 — Marcador `lab`:** `@pytest.mark.lab`, opt-in (`pytest -m lab`), fora da suíte padrão de ~20 s. `pyte` entra no extra `dev`. Documentar em `.claudex/tooling.md` §1.
- [x] **1B.1 — V-09 (rede e download):** `vector_store` passa a usar só modelo em cache (`local_files_only`); sem cache, cai no BM25 e o recall avisa **uma vez** por sessão. Instalação do modelo por comando explícito do Senhor (consentimento), com progresso pelo sink; `HF_HUB_DISABLE_PROGRESS_BARS` e telemetria desligados. Nenhum tqdm no terminal.
- [x] **1B.2 — V-10 e V-17 (stream):** (a) reproduzir em teste vermelho; (b) commit de bloco de código apenas fechado; (c) cancelamento grava a cauda do `Live` no histórico antes da mensagem de interrupção.
- [x] **1B.3 — V-11 (input durante o turno):** **spike** de até meio dia: leitura leve de teclas durante o turno com eco numa linha abaixo do spinner, sem criar janela horizontal extra no prompt (regra 3). Critério de adoção: sem linha fantasma em pty, em 3 larguras. **Plano B**, adotado se o spike falhar: indicador `1 na fila` sem eco. Registrar a escolha no `sprint-1.md` §8.1.
- [x] **1B.4 — V-12 e V-13 (ferramenta e modal):** cronômetro da ferramenta inicia na execução; a espera de aprovação é medida à parte e não aparece no tempo. Sob o modal PEP, linha de decisão (`✔ aprovado` ou `✖ negado`); a status line continua visível enquanto o modal está aberto. Nível exibido segue o PEP (docs corrigidas).
- [x] **1B.5 — V-14, V-15, V-16 (teclas e menu):** Esc com menu aberto chama `cancel_completion()`; Alt+E expande **com cabeçalho** (`✔ Bash: ... · saída completa`); alias para Alt+Shift+E; Ctrl+C com menu limpa sem resíduo e mostra `Ctrl+C de novo para sair` por 2 s.
- [x] **1B.6 — V-05 e V-06 (CPR):** rodapé independente de CPR (ADR-040); suprimir o aviso do prompt_toolkit quando o terminal não responde; tabela de terminais suportados em `CLI_DESIGN_SYSTEM.md`.
- [x] **1B.7 — Aviso de travamento:** após 5 s sem token com o turno ativo, linha discreta `sem resposta há 5s · Ctrl+C cancela` (o spinner já indica vida, não indica espera anormal).

### 🚫 Fora de Escopo
- Qualquer cor, layout, glifo ou texto novo de identidade (Sprint 2). Mensagens novas desta sprint usam os tokens e glifos atuais.
- Modelo real em teste automático. A rodada com o OpenRouter free (<= 15 req) é manual, com `ORION_LIVE=1`, ao final.
- Substituir `scripts/dogfood/` ou o `ptywright`.

---

## 5. Arquitetura & Arquivos Afetados

```
tests/lab/{__init__,conftest,launcher,pty_driver,scripted_provider,probes,texts}.py [novo]
tests/lab/scenarios/test_{first_turn_offline,stream,tools_and_pep,prompt_keys}.py [novo]
tests/lab/baseline.json                                        [novo]
tests/unit/test_tui_stability.py                               [novo] renderer, TypeAhead, teclas, embeddings offline
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

**Data:** 11/11/2026, na mesma sessão da spec (comando do Senhor). Branch `feat/v0.5.1-sprint-1`; spec em `5e408b0`.

**Rodada vermelha (código da v0.5.0, harness novo):** 11 de 15 cenários falharam pelo motivo esperado (V-05/06, V-09, V-10, V-11, V-12, V-13, V-14, V-15, V-16, aviso de travamento). Quatro passaram: cadência, janela viva, primeiro envio sem ruído (falso verde, ver desvio 2) e **cancelamento (V-17)**.

**Entregue**
* **1A — `tests/lab/`:** `pty_driver.LabTerminal` (pty + pyte, responde CPR, `cpr=False`, UTF-8 incremental, amostragem e CPU via `/proc`), `scripted_provider` (roteiros em JSON por palavra-chave, passos por resultado de tool, pausa e erro), `launcher` (mesmo caminho do `orion-agent`), `probes` + `baseline.json`, `conftest` com `open_lab` e `NetworkTrap`. 15 cenários em 4 arquivos. Marcador `lab` opt-in; `pyte` no extra `dev`.
* **V-09 (`memory/vector_store.py`, `auto_recall.py`, `/memory model`):** `load_embedding_model` só lê cache (`local_files_only`), primeiro em `~/.orion/models/fastembed`, depois no cache padrão do fastembed; sem modelo levanta `EmbeddingModelUnavailable` na hora. loguru do fastembed, barras do HF Hub, telemetria e `UserWarning` silenciados. `AutoRecall` avisa **uma vez** por sessão; `/memory model` mostra o estado e `/memory model install` baixa com spinner do console e religa a busca vetorial. **Causa raiz extra:** o cache padrão do fastembed é `/tmp/fastembed_cache`, apagado no reboot: o download de 67 MB voltava a cada reinício.
* **V-10 (`stream_renderer.py`):** duas causas, ambas corrigidas. (a) `_TailWindow`: a parte viva nunca passa de `altura - rodapé - 2` linhas e mostra a cauda (`· N linhas acima, completas ao fim do bloco`). (b) Corrida no Rich: o lock do `Live` só cobre o cálculo de quantas linhas apagar; se a thread de refresh desenha um quadro mais alto antes da escrita, sobram linhas. `_print` imprime sob o lock do Live. Prova: renderer antigo falhou 3/3; novo passou 2/2; novo sem a trava falhou 1 em 3.
* **V-11 (`prompt.py`, `cli.py`):** spike **adotado** (`TypeAhead`): durante o turno o terminal fica em `cbreak` (sem eco, Ctrl+C segue gerando SIGINT), as teclas viram `❯ texto` na parte viva, Enter enfileira (`· 1 na fila`). Modais pausam a leitura via `on_pause`/`on_resume` do renderer. Depois do turno, os pedidos da fila saem primeiro (com o bloco régua/❯/régua desenhado por `echo_submitted`) e o texto incompleto volta já digitado no prompt. Só em turnos do agente, nunca em slash commands (que abrem apps próprios do prompt_toolkit).
* **V-12:** `pause()` registra o instante; `resume()` desloca o início das ferramentas em execução pelo tempo pausado.
* **V-13 (`modal.py`, `panels.py`, `session.py`):** o modal mostra a status line enquanto aberto (`footer`); ao decidir, o histórico guarda o diálogo **sem** as teclas e a linha `✔ aprovado` (`· sempre permitir`, `· editado: …`) ou `✖ negado`.
* **V-14:** cabeçalho `✔ Bash: … · saída completa` na expansão; aliases Alt+Shift+E e Alt+Shift+R.
* **V-15:** Esc com o menu aberto (`eager`) fecha o menu e mantém o texto. Sem `eager`, o Esc ficava preso como prefixo dos atalhos Alt+tecla até a próxima tecla.
* **V-16:** o `HSplit` do prompt alinhado ao fundo (`VerticalAlign.BOTTOM`): o espaço do menu fechado não vira linhas vazias abaixo da status line. Aviso `Ctrl+C de novo para sair (ou /exit)`.
* **V-05/V-06:** causa confirmada no prompt_toolkit: a barra inferior do `PromptSession` tem filtro `renderer_height_is_known`, falso sem CPR. A status line virou uma janela própria no mesmo lugar (`~is_done`), e o callback de aviso do CPR foi removido.
* **1B.7:** `sem resposta há Ns · Ctrl+C cancela` após 5 s sem evento do provedor, fora de ferramenta em execução e de modal.

**Desvios e decisões**
1. **V-17 era falso positivo.** O cenário passou já no código antigo: na sonda de 11/11 o Ctrl+C chegou cedo (o cálculo contava a partida do ORION), não após 60% da resposta. O teste fica como regressão.
2. **Falso verde no V-09:** o `tests/conftest.py` raiz liga `ORION_RECALL=0` em todo teste e os processos do lab herdavam. O lab agora força `ORION_RECALL=1` e usa o `NetworkTrap` (proxy que conta conexões) no lugar de um proxy morto. Com isso o vermelho apareceu: 11 conexões, ~40 s bloqueado em retentativas e linhas `ERROR` do loguru na TUI.
3. **Artefatos de harness corrigidos antes de concluir:** decodificação UTF-8 por leitura (caracteres de borda partidos simulavam quadros fantasma) e alimentação do pyte por duas threads num repro offline. Nenhuma correção de produto foi aceita só com base nesses repros.
4. **`VerticalAlign.BOTTOM` vale para o layout com dock.** A Sprint 2 remove o dock e precisa revisar o alinhamento (anotado em `sprint-2.md`).
5. **1A.4 (CPU) sem otimização nesta sprint:** medido no lab, a CPU do ORION durante um stream de ~2,2 mil caracteres a ~200 car/s é **~10% de um núcleo** (10,2% a 10,8%, baseline 10,5%), e zero em repouso. O número de ~20% da sonda de 11/11 estava superestimado. No renderer isolado: 1,07 s (antigo) contra 1,00 s (novo) para o mesmo stream. O custo é o refresh do Live reparseando o Markdown da cauda a 12 Hz (`cProfile`: `Live.refresh` → `render_lines` → `Markdown.__rich_console__`). Cadência medida: 11,9 a 12,3 atualizações/s, maior pausa de 0,12 a 0,14 s após o primeiro caractere (gate do CA-02: >= 10 e <= 0,3 s).
6. **Rodada com o OpenRouter free não feita:** a chave não está neste ambiente (`OPENROUTER_API_KEY` ou `~/.orion/openrouter_api_key`). Fica pendente com o Senhor.

---

## 9. Critérios de Parada

1. Qualquer cenário do lab que chame rede, provedor pago ou escreva fora do `HOME` temporário.
2. Correção que reintroduza linha fantasma nas duas réguas do prompt (F-07/F-08).
3. Mudar `core/` ou o PEP além do necessário para V-12/V-13.
4. O spike V-11 consumir mais de meio dia sem prova: adotar o plano B e seguir.
5. Redução de CPU que derrube a cadência abaixo de 10 atualizações por segundo.
