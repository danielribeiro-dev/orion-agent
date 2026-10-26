# Sprint — [v0.3.0] Sprint 4: Resiliência Universal (Hardware-Friendly), Salvaguarda Cognitiva & Nuclear Step-Up Auth

> **Status:** ✅ Concluída  
> **Versão Relacionada:** v0.3.0 (Model Gateway, Real-Time Cost Ledger & Offline Resilience)  
> **Responsável / Agente:** Daniel Dev & Antigravity  
> **Data de Início:** 2026-10-26  
> **Data de Conclusão:** 2026-10-26  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** 
  1. Construir o subsistema de **Resiliência Universal & Circuit Breaker** do ORION com **Salvaguarda Cognitiva**:
     - **Hardware-Friendly:** O sistema **nunca** força o uso de modelos locais nem baixa modelos em background sem permissão; usuários com máquinas modestas não sofrem com consumo excessivo de RAM/CPU.
     - **Regra de Ouro da Integridade de Código:** Quando um modelo de potência (`HEAVY`, ex: Claude Opus / Sonnet 4.5) falha por erro de API, saldo ou rede, o sistema **nunca** realiza downgrade silencioso para um modelo fraco continuar programando. Em vez disso, se houver modelo equivalente de fronteira configurado (ex: Gemini 2.5 Pro / GPT-4o), chaveia para ele. Se não houver, chaveia para um modelo leve **apenas para dialogar com o usuário e explicar a causa da interrupção**, travando mutações de arquivos até o restabelecimento do modelo de topo.
     - **Local Fallback Opt-in:** Suporte a Ollama estritamente opcional (`local_fallback_enabled: false` por padrão).
     - **Modo Suspenso Gracioso:** Caso ocorra corte total de conexão sem fallback, a sessão é pausada com persistência de estado (SQLite) sem travar a máquina.
  2. Implementar no Policy Enforcement Point (PEP) a **Autonomia Adaptativa com `CommandTrustLedger`** (cache de comandos conhecidos e seguros) e a trava inviolável do **Nuclear Threshold**, acionando obrigatoriamente um **popup de senha/biometria do sistema operacional** (Polkit/`pkexec`, `zenity` ou diálogo nativo mascarado em SSH) para operações de alto impacto destrutivo em qualquer modo (inclusive auto).
* **Dependências Prévias:** Sprints 1, 2 e 3 da v0.3.0 concluídas.
* **Entregável Verificável:** Módulos `circuit_breaker.py`, `local_ollama.py`, `trust_ledger.py` e `nuclear.py` com testes automatizados cobrindo salvaguarda de código, circuit breaker, trava nuclear e integridade de hardware modesto.

---

## 2. Contexto de Engenharia

* **Por que esta sprint existe:** Para blindar o ORION contra os maiores riscos de agentes autônomos em ambientes reais de desenvolvimento:
  1. *Degradação silenciosa perigosa:* Modelos fracos gerando código complexo causam destruição de arquitetura e bugs sutis. A troca deve ser transparente e segura (apenas conversacional para notificação ou entre modelos de mesmo porte).
  2. *Respeito aos limites do hardware:* Desenvolvedores usam notebooks modestos com pouca memória. Executar VS Code + terminal + agente + Ollama com modelo local provocaria congelamento do sistema. Modelos locais devem ser puramente opt-in.
  3. *Destruição acidental ou alucinação destrutiva:* Em modo auto ou modo ambiente de voz (v0.5.0), uma fala mal interpretada (*"apaga tudo e recomeça"*) não pode destruir o sistema operacional. O popup de senha do SO garante que apenas a presença física consciente autorize operações críticas.
* **Decisões arquiteturais associadas:** ADR-017 (Command Trust Ledger & Autonomia Adaptativa), ADR-018 (Nuclear Threshold & Popup Obrigatório do SO), ADR-019 (Resiliência Universal & Salvaguarda Cognitiva sem Downgrade Cego).

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Estado Inicial (Antes da Sprint) | Estado Final Esperado (DoD) |
| :--- | :--- | :--- |
| **Resiliência a Falhas** | Falha e interrompe se API cair | Retentativas com backoff; chaveamento equi-tier para código; Safe Holding para conversa |
| **Integridade de Código** | Inexistente (risco de downgrade) | **Proibido** rebaixar modelo de código para modelo fraco; mutações são bloqueadas no Safe Holding |
| **Uso de Recursos Locais** | Risco de sobrecarga | Zero download não autorizado; Ollama desativado por padrão; pausa graciosa se offline |
| **Comandos Conhecidos** | Pergunta toda vez no modo manual | Lembra comandos seguros executados com sucesso (`command_trust`) |
| **Ações Catastróficas** | Prompt de texto comum `[Y/n]` | **Popup nativo do SO** com autenticação do dispositivo em todos os modos |

---

## 4. Escopo da Sprint

### ✅ No Escopo (In Scope)
- [x] Implementação de `CircuitBreaker` e Gerenciador de Resiliência em `src/orion/gateway/circuit_breaker.py`:
  - Retentativas com jitter exponencial em erros 429, 502, 503, 504 e timeout.
  - Salvaguarda Cognitiva: chaveamento para modelo de mesma potência (`equi_tier_frontier`) ou ativação de `SAFE_HOLDING`.
  - Modo `SAFE_HOLDING`: modelo leve explica ao desenvolvedor o motivo da parada (falha na API, saldo de créditos, timeout) e permite diálogo, mas bloqueia `write_file`, `edit_file` e comandos mutantes até a volta do modelo de topo.
  - Salvaguarda Inviolável: se o usuário escolheu intencionalmente um modelo leve como diário (`intentional_lite_mode=True`), `SAFE_HOLDING` NUNCA é ativado e ferramentas permanecem 100% disponíveis.
  - Modo `OFFLINE_SUSPENDED`: pausa graciosa em caso de queda de rede sem fallback local, salvando checkpoint no banco.
- [x] Implementação de `LocalOllamaProvider` em `src/orion/gateway/providers/local_ollama.py`:
  - Adaptador opcional para Ollama via HTTP assíncrono.
  - Zero auto-download e zero auto-start; checagem rápida (`/api/tags`) de disponibilidade.
- [x] Implementação de `CommandTrustLedger` em `src/orion/governance/trust_ledger.py`:
  - Armazenamento SQLite de assinaturas de comandos já aprovados e bem-sucedidos.
  - Comandos conhecidos e não-destrutivos (`git status`, `pytest`, `npm test`) não interrompem o usuário em modo auto.
- [x] Implementação de `NuclearSafetyGate` em `src/orion/governance/nuclear.py`:
  - Classificação estrita de *Blast Radius*: detecta `rm -rf`, deleção massiva, modificações em `/`, `/etc`, `~/.ssh`, `dd`, `mkfs`.
  - Disparo de autenticação nativa do sistema operacional:
    - Com display gráfico: aciona `zenity --password`, `kdialog` ou `pkexec`.
    - Headless / SSH: diálogo mascarado seguro no `/dev/tty` (`getpass`).
- [x] Integração no `PolicyEnforcementPoint` (`src/orion/governance/pep.py`):
  - Consulta ao `CommandTrustLedger` e ao `NuclearSafetyGate`.
  - Bloqueio de mutações se o Circuit Breaker estiver em `SAFE_HOLDING` (e não em `intentional_lite_mode`).
- [x] Testes unitários com mocks em `tests/unit/test_circuit_breaker.py`, `tests/unit/test_local_ollama.py`, `tests/unit/test_trust_ledger.py` e `tests/unit/test_nuclear.py`.

### 🚫 Fora de Escopo (Out of Scope / Anti-Metas)
- Não conectar microfone ou sintetizador de áudio real nesta sprint (escopo da v0.5.0).
- Não criar sandbox de contêineres Bubblewrap (escopo da v1.5.0).
- Não baixar automaticamente pesos de modelos locais de IA na máquina do desenvolvedor.

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/
├── gateway/
│   ├── circuit_breaker.py             # Circuit breaker, salvaguarda cognitiva e gerenciador de resiliência
│   └── providers/
│       └── local_ollama.py            # Adaptador Ollama opcional e leve (zero auto-download)
└── governance/
    ├── trust_ledger.py                # CommandTrustLedger com cache de assinaturas confiáveis
    ├── nuclear.py                     # Detector de Blast Radius destrutivo e disparador de popup do SO
    └── pep.py                         # Integração de trava nuclear, trust ledger e trava de Safe Holding
tests/unit/
├── test_circuit_breaker.py            # Testes de retentativa, equi-tier, safe holding e modo suspenso
├── test_local_ollama.py               # Testes do adaptador local e tratamento de indisponibilidade
├── test_trust_ledger.py               # Testes do cache de comandos confiáveis
└── test_nuclear.py                    # Testes de detecção de comandos destrutivos e popup do SO
```

---

## 6. Contratos de Código & Tipagem

```python
from enum import Enum
from pydantic import BaseModel

class CircuitState(str, Enum):
    CLOSED = "closed"              # Operação normal
    OPEN = "open"                  # Falhas frequentes; retentativas em pausa
    HALF_OPEN = "half_open"        # Testando recuperação do serviço
    SAFE_HOLDING = "safe_holding"  # Modelo de topo fora; modo conversacional ativo, escrita bloqueada

class BlastRadius(str, Enum):
    BENIGN = "benign"                 # Leitura, build, teste
    WORKSPACE_MUTATION = "workspace" # Criação/edição em diretório permitido
    SYSTEM_ELEVATED = "system"       # sudo apt install (seguro após 1ª vez)
    NUCLEAR_DESTRUCTIVE = "nuclear"  # rm -rf, wipe, mkfs, /etc (SEMPRE exige autenticação do SO)

class CommandSignature(BaseModel):
    command_hash: str
    canonical_pattern: str
    first_executed_at: str
    execution_count: int
    last_exit_code: int

class NuclearChallengeResult(BaseModel):
    authorized: bool
    method_used: str  # 'polkit_gui', 'zenity', 'tty_fallback'
    duration_seconds: float
```

---

## 7. Critérios de Aceite (DoD)

- [x] Falha persistente no modelo de topo (`HEAVY`) sem modelo equi-tier ativa `SAFE_HOLDING`, avisando o desenvolvedor e impedindo mutações de código.
- [x] Chaveamento para modelo de mesma potência (`equi_tier_frontier`) preserva a capacidade de geração de código.
- [x] Se o usuário configurar deliberadamente um modelo leve como rotina (`intentional_lite_mode=True`), `SAFE_HOLDING` NUNCA é ativado e ferramentas continuam 100% livres.
- [x] A flag `local_fallback_enabled` é `False` por padrão e nunca baixa modelos automaticamente.
- [x] Corte de rede sem fallback entra em modo `OFFLINE_SUSPENDED` sem congelar a máquina e sem disparar consumo de CPU/RAM.
- [x] Comandos inofensivos (`git status`, `npm test`) já executados rodam sem exibir prompt em modo auto.
- [x] Comandos com `sudo` benignos (`sudo apt install htop`) pedem confirmação apenas na primeira vez em modo auto.
- [x] Qualquer comando avaliado como `NUCLEAR_DESTRUCTIVE` dispara autenticação obrigatória do sistema operacional em todos os modos.
- [x] Suíte de testes com cobertura $\ge 85\%$ (**92.31% atingido**: `circuit_breaker.py`=94%, `local_ollama.py`=89%, `nuclear.py`=94%, `pep.py`=91%, `trust_ledger.py`=92%).
