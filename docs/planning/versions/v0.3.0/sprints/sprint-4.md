# Sprint — [v0.3.0] Sprint 4: ORION Imortal (Failover Local Leve) & Nuclear Step-Up Auth

> **Status:** 📋 Planejado  
> **Versão Relacionada:** v0.3.0 (Model Gateway, Real-Time Cost Ledger & Offline Resilience)  
> **Responsável / Agente:** Daniel Dev & Antigravity  
> **Data de Início:** A definir (Fase 3)  
> **Data de Conclusão:** —  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** 
  1. Construir o subsistema **ORION Imortal**, implementando um *circuit breaker* de conectividade que executa failover automático em menos de 2 segundos para inferência local via Ollama utilizando a família leve **`qwen2.5-coder:1.5b`** ou **`qwen2.5-coder:3b`** (~1.5GB a 2.8GB de RAM), garantindo sobrevivência operacional mesmo com a internet desligada.
  2. Implementar no Policy Enforcement Point (PEP) a **Autonomia Adaptativa com `CommandTrustLedger`** (cache de comandos conhecidos e seguros) e a trava inviolável do **Nuclear Threshold**, acionando obrigatoriamente um **popup de senha/biometria do sistema operacional** (Polkit/`pkexec`, `zenity` ou diálogo nativo) para operações de alto impacto destrutivo em qualquer modo (inclusive auto).
* **Dependências Prévias:** Sprints 1, 2 e 3 da v0.3.0 concluídas.
* **Entregável Verificável:** Failover para Ollama local validado em teste automatizado simulando timeout/5xx com chaveamento < 2s, e interceptação de comandos perigosos disparando o popup gráfico do sistema operacional no Linux.

---

## 2. Contexto de Engenharia

* **Por que esta sprint existe:** Para blindar o ORION contra os dois maiores riscos de agentes autônomos:
  1. *Dependência de conectividade:* Agentes que morrem sem internet não podem ser considerados orquestradores de sistema operacional soberanos. O modelo local leve permite continuar codificando e raciocinando em qualquer máquina modesta.
  2. *Destruição acidental ou alucinação destrutiva:* Em modo auto ou modo ambiente de voz (v0.5.0), uma fala mal interpretada enquanto o usuário está conversando ou deitado (*"apaga tudo e recomeça"*) não pode destruir o sistema operacional. O popup de senha do SO garante que apenas a presença física consciente autorize operações críticas.
* **Decisões arquiteturais associadas:** ADR-017 (Command Trust Ledger & Autonomia Adaptativa), ADR-018 (Nuclear Threshold & Popup Obrigatório do SO), ADR-019 (Failover Local Leve Qwen Coder).

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Estado Inicial (Antes da Sprint) | Estado Final Esperado (DoD) |
| :--- | :--- | :--- |
| **Tolerância Offline** | Falha se API cair | Failover automático em $< 2$s para Ollama (`qwen2.5-coder:1.5b/3b`) |
| **Comandos Conhecidos** | Pergunta toda vez no modo manual | Lembra comandos seguros executados com sucesso (`command_trust`) |
| **Uso de `sudo`** | Bloqueado estaticamente no PEP v0.1.0 | `sudo` comum (ex: `apt install`) memorizado após 1ª aprovação |
| **Ações Catastróficas** | Prompt de texto comum `[Y/n]` | **Popup nativo do SO** com senha do dispositivo em todos os modos |

---

## 4. Escopo da Sprint

### ✅ No Escopo (In Scope)
- [ ] Implementação de `CircuitBreaker` e `LocalOllamaProvider` em `src/orion/gateway/`:
  - Ping periódico de saúde de conectividade para endpoints na nuvem.
  - Chaveamento instantâneo para Ollama local se status for 5xx, timeout ou desconectado.
  - Suporte específico ao modelo `qwen2.5-coder:1.5b` ou `qwen2.5-coder:3b` rodando localmente na porta padrão do Ollama (`http://localhost:11434`).
  - Reconciliação sem conflito quando a conexão de rede retornar.
- [ ] Implementação de `CommandTrustLedger` em `src/orion/governance/trust_ledger.py`:
  - Armazenamento SQLite/persistente de assinaturas de comandos já aprovados pelo usuário e bem-sucedidos.
  - Regra de execução: comandos conhecidos e não-destrutivos (inclusive `sudo apt update`, `npm test`) não interrompem o usuário em modo auto/accept-edits.
  - Comandos inéditos solicitam confirmação na primeira vez e entram no cache após aprovação.
- [ ] Implementação de `NuclearSafetyGate` em `src/orion/governance/nuclear.py`:
  - Classificação estrita de *Blast Radius*: detecta `rm -rf`, deleção de múltiplos arquivos, modificações fora do workspace em `/`, `/etc`, `~/.ssh`, `dd`, `mkfs`.
  - Disparo do popup nativo do sistema operacional:
    - Se `$DISPLAY` ou `$WAYLAND_DISPLAY` estiver presente: aciona `pkexec`, `zenity --password` ou `kdialog --password`.
    - Fallback para ambientes puramente headless/SSH sem display: diálogo mascarado seguro no `/dev/tty` (`getpass`).
  - Preparação para anúncio de voz na v0.5.0 (*"Senhor, posso executar o comando destrutivo [detalhes]? Por favor, autorize no dispositivo."*).
- [ ] Testes unitários e mocks em `tests/unit/test_circuit_breaker.py` e `tests/unit/test_nuclear.py`.

### 🚫 Fora de Escopo (Out of Scope / Anti-Metas)
- Não conectar microfone ou sintetizador de áudio real nesta sprint (escopo da v0.5.0).
- Não criar sandbox de contêineres Bubblewrap (escopo da v1.5.0).

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/
├── gateway/
│   ├── circuit_breaker.py             # Monitor de conectividade e orquestrador de failover offline
│   └── providers/
│       └── local_ollama.py            # Adaptador Ollama local (qwen2.5-coder:1.5b/3b)
└── governance/
    ├── trust_ledger.py                # CommandTrustLedger com cache de assinaturas confiáveis
    ├── nuclear.py                     # Detector de Blast Radius destrutivo e disparador de popup do SO
    └── pep.py                         # Integração da checagem adaptativa e trava nuclear no evaluate()
tests/unit/
├── test_circuit_breaker.py            # Testes de chaveamento offline < 2s
└── test_nuclear.py                    # Testes de detecção de comandos destrutivos e disparo de popup
```

---

## 6. Contratos de Código & Tipagem

```python
from enum import Enum
from pydantic import BaseModel

class BlastRadius(str, Enum):
    BENIGN = "benign"                 # Leitura, build, teste
    WORKSPACE_MUTATION = "workspace" # Criação/edição em diretório permitido
    SYSTEM_ELEVATED = "system"       # sudo apt install, systemctl (seguro após 1ª vez)
    NUCLEAR_DESTRUCTIVE = "nuclear"  # rm -rf, wipe, mkfs, /etc (SEMPRE exige popup de senha do SO)

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

- [ ] Simulação de corte de rede na nuvem direciona a inferência para o Ollama local em menos de 2 segundos.
- [ ] Comandos inofensivos (`git status`, `npm test`) já executados rodam sem exibir prompt em modo auto.
- [ ] Comandos com `sudo` benignos (`sudo apt install htop`) pedem confirmação apenas na primeira vez em modo auto.
- [ ] Qualquer comando avaliado como `NUCLEAR_DESTRUCTIVE` dispara o popup nativo de autenticação do sistema operacional em todos os modos.
- [ ] Suíte de testes com cobertura $\ge 85\%$.
