# Sprint — [v0.2.0] Sprint 3: The 5-Sphere Memory, Cognitive Tools & Remote HITL Connector

> **Status:** 📋 Planejado  
> **Versão Relacionada:** v0.2.0 (Cognitive Continuity: The 5-Sphere Memory, Universal Skills Standard & Dynamic Compaction)  
> **Responsável / Agente:** Daniel Dev & Antigravity  
> **Data de Início:** A definir (Fase 2)  
> **Data de Conclusão:** —  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Implementar a **Arquitetura das 5 Esferas Cognitivas** do ORION:
  1. **`user_profile`:** Perfil do usuário com nome, forma preferida de tratamento (`"Senhor"`), matriz tipada de proficiência em ferramentas (`tool_mastery`) e configuração de canais remotos.
  2. **`system_identity`:** Identidade dual com **Origem Imutável** (concebido por Daniel, github: `danielribeiro-dev`) e **Persona Ativa Modular** (Jarvis: polido, elegante, minimalista em terminal e didático em explicações).
  3. **`system_environment`:** Módulo de telemetria passiva via `psutil` (RAM livre, CPU load, modo de display Wayland/X11 vs Headless) com o **Headroom Guard** (bloqueio determinístico de navegadores se RAM livre $< 1.5\text{ GB}$).
  4. **`project_decisions`:** Armazenamento relacional de ADRs e regras com máquina de estados anti-envenenamento (`CONFIRMED`, `INFERRED`, `DEPRECATED`) e sincronização com `MEMORY.md` (teto de 200 linhas).
  5. **`manifest.py`:** Gerador do **Cognitive Manifest** ultra-compacto ($< 250$ tokens) para injeção no System Prompt via *Progressive Cognitive Unpacking (PCU)*.
  6. **Ferramentas Cognitivas no ReAct:** `memorize`, `recall`, `deprecate_fact`, `inspect_environment`.
  7. **Remote HITL Connector:** Conector assíncrono via **Telegram Bot** com aprovação remota de PEP (Level 2 ou 3) com botões inline quando o terminal estiver inativo ($> 180$s).
* **Dependências Prévias:** Sprint 1 e 2 concluídas (FTS5 BM25 e FastEmbed RRF funcionais).
* **Entregável Verificável:** Módulos em `src/orion/memory/`, `src/orion/runtime/environment.py` e `src/orion/core/identity.py` totalmente testados, com zero afogamento de contexto e governança determinística.

---

## 2. Contexto de Engenharia

* **Por que esta sprint existe:** Para transformar o ORION no agente pessoal mais agradável, eficiente e consciente do mundo:
  - Ele sabe quem é o seu usuário e como ele gosta de ser tratado (ex: *"Senhor"*).
  - Ele calibra sua didática conforme a maturidade do desenvolvedor em cada tecnologia.
  - Ele nunca alucina quem o criou nem perde sua persona refinada.
  - Ele protege o hardware do usuário, sabendo em tempo real se tem RAM suficiente para abrir browsers sem travar a máquina.
  - Ele nunca envenena sua memória com suposições descartadas.
  - Ele permite que o desenvolvedor tome um café longe da mesa sem travar a execução, autorizando ações críticas pelo celular via Telegram.
* **Decisões arquiteturais associadas:** ADR-004, ADR-006, ADR-013, ADR-014 (5 Esferas e PCU), ADR-015 (Environment Guard), ADR-016 (Telegram HITL).

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Estado Inicial (Antes da Sprint) | Estado Final Esperado (DoD) |
| :--- | :--- | :--- |
| **Perfil do Usuário** | Inexistente | `UserProfile` estruturado com `call_sign="Senhor"` e `ToolMastery` |
| **Identidade do Sistema** | Hardcoded simples | Camada Imutável (Daniel/danielribeiro-dev) + Persona Modular Jarvis |
| **Hardware Awareness** | Agente cego para RAM/CPU | `EnvironmentMonitor` com `HeadroomGuard` determinístico |
| **Poluição de Prompt** | Risco de injeção pesada | `CognitiveManifest` com teto rígido de $< 250$ tokens no boot |
| **Prevenção de Poisoning** | Inexistente | Máquina de estados `CONFIRMED`, `INFERRED`, `DEPRECATED` |
| **Aprovação Fora da Mesa** | Travado no terminal local | Ping seguro no Telegram Bot com botões `[Aprovar]` / `[Rejeitar]` |
| **Ferramentas no ReAct** | Apenas as 5 primitivas de SO | `memorize`, `recall`, `deprecate_fact`, `inspect_environment` |

---

## 4. Escopo da Sprint

### ✅ No Escopo (In Scope)
- [ ] Modelos de dados em `src/orion/memory/models.py`:
  - `FactStatus`: `CONFIRMED`, `INFERRED`, `DEPRECATED`.
  - `FactCategory`: `USER_PREFERENCE`, `PROJECT_ARCHITECTURE`, `CODING_STANDARD`, `INFRASTRUCTURE`.
  - `ToolMasteryLevel`: `EXPERT`, `ADVANCED`, `INTERMEDIATE`, `BEGINNER`.
  - `UserProfile`: `name`, `call_sign`, `tool_mastery`, `remote_channel`, `telegram_chat_id`, `inactivity_timeout_seconds`.
  - `SystemIdentity`: Origem imutável + Persona ativa (nome, estilo, regras de tom).
  - `EnvironmentTelemetry`: RAM livre/total, CPU load, display mode, GPU info, headroom status.
- [ ] Implementação de `EnvironmentMonitor` em `src/orion/runtime/environment.py`:
  - Telemetria passiva via `psutil` (com fallback seguro para `/proc/meminfo` e `/proc/loadavg`).
  - Método `is_safe_for_browser() -> bool` (retorna `False` se RAM livre $< 1.5\text{ GB}$).
- [ ] Implementação de `IdentityManager` em `src/orion/core/identity.py`:
  - Definição canônica de origem imutável (Daniel / `danielribeiro-dev`).
  - Carregador e validador da Persona ativa (`~/.orion/persona.json`).
- [ ] Implementação de `FactsStore` em `src/orion/memory/facts_store.py`:
  - Persistência em SQLite relacional com máquina de estados de certeza tipada.
  - Regra de precedência estrita: fatos `INFERRED` nunca sobrescrevem chaves com status `CONFIRMED`.
- [ ] Implementação de `CognitiveManifestGenerator` em `src/orion/memory/manifest.py`:
  - Sintetizador do bloco ultra-compacto `<COGNITIVE_MANIFEST>` ($< 250$ tokens).
- [ ] Sincronizador de arquivo `file_syncer.py`:
  - Mantém `.orion/memory/MEMORY.md` formatado com teto estrito de 200 linhas.
- [ ] Conector Out-of-Band Telegram em `src/orion/memory/hitl_telegram.py`:
  - Disparo de mensagem de aprovação com inline keyboard `[Aprovar]` / `[Rejeitar]` quando inatividade $> 180$s em ações PEP Level 2/3.
  - Polling assíncrono ou webhook de callback com verificação estrita de `chat_id` e TTL de 10 minutos.
- [ ] Implementação das Ferramentas Cognitivas em `src/orion/memory/tools.py`:
  - `MemorizeTool`, `RecallTool`, `DeprecateFactTool`, `InspectEnvironmentTool`.
- [ ] Testes unitários cobrindo todas as esferas, teto de tokens do manifesto, anti-poisoning e Telegram mock.

### 🚫 Fora de Escopo (Out of Scope / Anti-Metas)
- Não carregar o padrão Universal Agent Skills (`SKILL.md`) (escopo da Sprint 4).
- Não gerenciar branches ou compactação de contexto (escopo da Sprint 4).

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/
├── memory/
│   ├── __init__.py
│   ├── models.py                      # Modelos FactEntry, UserProfile, SystemIdentity, Telemetry
│   ├── facts_store.py                 # SQLite relacional com máquina de estados de certeza
│   ├── manifest.py                    # Gerador do Cognitive Manifest (< 250 tokens)
│   ├── file_syncer.py                 # Sincronizador de MEMORY.md (teto 200 linhas)
│   ├── hitl_telegram.py               # Conector Out-of-Band Telegram HITL
│   └── tools.py                       # MemorizeTool, RecallTool, DeprecateFactTool, InspectEnvTool
├── runtime/
│   └── environment.py                 # Telemetria de hardware (psutil) e Headroom Guard
├── core/
│   └── identity.py                    # Origem Imutável e Persona Engine
tests/
└── unit/
    ├── test_facts_store.py            # Testes de integridade e anti-poisoning
    ├── test_environment.py            # Testes de psutil e Headroom Guard (< 1.5GB)
    ├── test_identity.py               # Testes de origem Daniel e persona Jarvis
    ├── test_manifest.py               # Testes de teto orçamentário do manifesto (< 250 tokens)
    ├── test_hitl_telegram.py          # Testes com mock do Telegram Bot API
    └── test_memory_tools.py           # Testes das ferramentas cognitivas no ReAct
```

---

## 6. Contratos de Código & Tipagem

```python
from enum import Enum
from typing import Dict, Optional
from datetime import datetime
from pydantic import BaseModel, Field

class FactStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    INFERRED = "INFERRED"
    DEPRECATED = "DEPRECATED"

class FactCategory(str, Enum):
    USER_PREFERENCE = "USER_PREFERENCE"
    PROJECT_ARCHITECTURE = "PROJECT_ARCHITECTURE"
    CODING_STANDARD = "CODING_STANDARD"
    INFRASTRUCTURE = "INFRASTRUCTURE"

class ToolMasteryLevel(str, Enum):
    EXPERT = "expert"
    ADVANCED = "advanced"
    INTERMEDIATE = "intermediate"
    BEGINNER = "beginner"

class UserProfile(BaseModel):
    name: str = "Daniel"
    call_sign: str = "Senhor"
    tool_mastery: Dict[str, ToolMasteryLevel] = Field(default_factory=dict)
    remote_channel: str = "none"  # "telegram", "whatsapp", "none"
    telegram_chat_id: Optional[str] = None
    inactivity_timeout_seconds: int = 180

class PersonaConfig(BaseModel):
    name: str = "Jarvis"
    style: str = "Elegante, mordomo britânico, assertivo e conciso em terminal, didático em explicações"
    concise_shell_mode: bool = True
    didactic_theory_mode: bool = True

class EnvironmentTelemetry(BaseModel):
    ram_total_mb: float
    ram_available_mb: float
    cpu_load_1m: float
    display_mode: str  # "wayland", "x11", "headless"
    gpu_available: bool = False
    browser_safe: bool = True
```

---

## 7. Estratégia de Implementação (Passo a Passo)

1. **Passo 1:** Definir todos os modelos de dados e enums em `src/orion/memory/models.py`.
2. **Passo 2:** Criar o módulo `src/orion/runtime/environment.py` com detecção de RAM/CPU e a salvaguarda determinística `is_safe_for_browser()`.
3. **Passo 3:** Criar o módulo `src/orion/core/identity.py` com a origem canônica imutável de Daniel Ribeiro e carregamento de persona modular.
4. **Passo 4:** Implementar o `FactsStore` com SQLite relacional e regras estritas de blindagem contra *memory poisoning*.
5. **Passo 5:** Implementar o `CognitiveManifestGenerator` garantindo injeção com teto rígido de 250 tokens no boot.
6. **Passo 6:** Implementar o conector `hitl_telegram.py` para escalonamento remoto com mock para suíte de testes.
7. **Passo 7:** Implementar as 4 ferramentas cognitivas (`memorize`, `recall`, `deprecate_fact`, `inspect_environment`) integradas ao catálogo ReAct.
8. **Passo 8:** Escrever suíte de testes unitários com cobertura $\ge 90\%$.

---

## 8. Testes Automatizados & Critérios de Aceite (DoD)

### Cenários de Teste Obrigatórios
- **Teste 1:** Um fato `INFERRED` tenta sobrescrever uma chave `CONFIRMED` $\rightarrow$ Operação bloqueada deterministicamente.
- **Teste 2:** Simulação de RAM livre $< 1.5\text{ GB}$ $\rightarrow$ `is_safe_for_browser()` retorna `False` e emite alerta amigável.
- **Teste 3:** `CognitiveManifest` gerado para o system prompt consome comprovadamente $< 250$ tokens.
- **Teste 4:** Persona "Jarvis" e tratamento `"Senhor"` são carregados e refletidos na identidade sem apagar a autoria imutável de Daniel (`danielribeiro-dev`).
- **Teste 5:** Simulação de inatividade de 180s em comando PEP LEVEL_3 despacha payload de aprovação no mock do Telegram Bot API com callback verificado.
- **Teste 6:** Ferramentas `memorize`, `recall`, `deprecate_fact` e `inspect_environment` respondem adequadamente dentro do ReAct loop.

### Definition of Done (DoD)
- [ ] As 5 Esferas Cognitivas totalmente implementadas e tipadas com Pydantic v2.
- [ ] Cognitive Manifest operando com teto estrito de $< 250$ tokens.
- [ ] Environment Monitor com Headroom Guard ativo.
- [ ] Conector Out-of-Band Telegram Bot validado com testes mockados.
- [ ] Todas as 4 ferramentas cognitivas integradas ao ReAct Engine com governança PEP.
- [ ] `pytest tests/unit/test_facts_store.py tests/unit/test_environment.py tests/unit/test_identity.py tests/unit/test_manifest.py tests/unit/test_hitl_telegram.py tests/unit/test_memory_tools.py` passando com 100% de sucesso.
- [ ] Cobertura de testes dos módulos $\ge 90\%$.
