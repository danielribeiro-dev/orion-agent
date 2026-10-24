# Sprint — [v0.2.0] Sprint 3: Structured Knowledge, User Profile & Cognitive Memory Tools

> **Status:** 📋 Planejado  
> **Versão Relacionada:** v0.2.0 (Cognitive Continuity: Triple Memory, Agent Skills Standard & Dynamic Compaction)  
> **Responsável / Agente:** Daniel Dev & Antigravity  
> **Data de Início:** A definir (Fase 2)  
> **Data de Conclusão:** —  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Implementar a **Camada Estruturada de Fatos e Decisões** (Camada 3 da Memória Tríplice), a máquina de estados anti-envenenamento (`CONFIRMED`, `INFERRED`, `DEPRECATED`), a sincronização com o arquivo curado `MEMORY.md` (teto estrito de 200 linhas) e logs diários (`daily/YYYY-MM-DD.md`), e as **3 Ferramentas Cognitivas Nativas** no ReAct loop (`memorize`, `recall`, `deprecate_fact`) com auditoria PEP.
* **Dependências Prévias:** Sprint 1 e 2 concluídas (FTS5 BM25 e FastEmbed RRF funcionais).
* **Entregável Verificável:** Módulos `src/orion/memory/facts_store.py` e `src/orion/memory/tools.py` totalmente testados, permitindo que o modelo memorize fatos confirmados, consulte a linha do tempo por conta própria e revogue decisões antigas com integridade determinística.

---

## 2. Contexto de Engenharia

* **Por que esta sprint existe:** Agentes autônomos sofrem frequentemente de *Memory Poisoning* — quando uma hipótese descartada ou uma suposição errônea do LLM é gravada como fato definitivo na memória do sistema. Para evitar isso, os fatos do ORION possuem um ciclo de vida tipado e as informações explícitas do usuário (`CONFIRMED`) têm precedência absoluta sobre ilações do agente (`INFERRED`).
* **Como se encaixa na visão global:** Completa a tríade da Memória Tríplice e entrega os "braços" cognitivos para que o agente gerencie sua própria mente durante as sessões de trabalho.
* **Decisões arquiteturais associadas:** ADR-004 (Memória Tríplice), ADR-006 (Governança PEP), ADR-013 (Prevenção de Memory Poisoning & Ferramentas Cognitivas).

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Estado Inicial (Antes da Sprint) | Estado Final Esperado (DoD) |
| :--- | :--- | :--- |
| **Armazenamento de Fatos** | Inexistente | Tabela `structured_facts` com tipagem Pydantic v2 e enum `FactStatus` |
| **Índice em Disco** | Inexistente | `.orion/memory/MEMORY.md` sincronizado com teto de 200 linhas |
| **Prevenção de Poisoning** | Inexistente | Fatos inferidos nunca sobrescrevem fatos confirmados pelo usuário |
| **Ferramentas no ReAct** | Apenas as 5 primitivas de SO | `memorize`, `recall` e `deprecate_fact` disponíveis no catálogo de tools |

---

## 4. Escopo da Sprint

### ✅ No Escopo (In Scope)
- [ ] Implementação de `FactsStore` em `src/orion/memory/facts_store.py`:
  - Tabela SQLite `structured_facts` (key, value, category, status, confidence, updated_at).
  - Enum `FactStatus`: `CONFIRMED` (explícito pelo usuário), `INFERRED` (deduzido pelo modelo), `DEPRECATED` (revogado).
  - Regra de precedência estrita: tentativa de gravar fato `INFERRED` sobre chave existente com status `CONFIRMED` é rejeitada ou convertida em anotação secundária.
- [ ] Mecanismo de sincronização bidirecional de `MEMORY.md`:
  - Gera/atualiza o arquivo `.orion/memory/MEMORY.md` com fatos confirmados e arquitetura.
  - Teto rígido de 200 linhas: executa auto-purgamento ou sugere criação de arquivos de tópico se o limite for atingido.
- [ ] Implementação das 3 Ferramentas Cognitivas em `src/orion/memory/tools.py`:
  - `MemorizeTool`: registra novos fatos/regras com categorização e nível de confiança.
  - `RecallTool`: aciona a recuperação híbrida RRF sob demanda durante o turno de raciocínio.
  - `DeprecateFactTool`: invalida formalmente um fato desatualizado, registrando a justificativa.
- [ ] Integração com o Policy Enforcement Point (PEP): registro de auditoria append-only para qualquer mutação na memória estruturada.
- [ ] Testes unitários de validação anti-envenenamento, persistência em disco e execução de ferramentas.

### 🚫 Fora de Escopo (Out of Scope / Anti-Metas)
- Não carregar o padrão Universal Agent Skills (`SKILL.md`) (escopo da Sprint 4).
- Não gerenciar branches ou compactação de contexto (escopo da Sprint 4).

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/memory/
├── facts_store.py                     # FactsStore relacional com máquina de estados de certeza
├── file_syncer.py                     # Sincronizador de MEMORY.md e daily logs
├── tools.py                           # MemorizeTool, RecallTool, DeprecateFactTool
└── models.py                          # FactEntry, FactStatus, FactCategory
tests/
└── unit/
    ├── test_facts_store.py            # Testes de integridade e anti-poisoning
    ├── test_file_syncer.py            # Testes de teto de 200 linhas em MEMORY.md
    └── test_memory_tools.py           # Testes das ferramentas no ReAct loop
```

---

## 6. Contratos de Código & Tipagem

```python
from enum import Enum
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

class FactEntry(BaseModel):
    key: str
    value: str
    category: FactCategory
    status: FactStatus = FactStatus.INFERRED
    reason: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

---

## 7. Estratégia de Implementação (Passo a Passo)

1. **Passo 1:** Definir os modelos e enums `FactStatus` e `FactCategory` em `src/orion/memory/models.py`.
2. **Passo 2:** Implementar `FactsStore` com SQLite relacional garantindo proteção contra sobrescrita indevida de dados confirmados.
3. **Passo 3:** Implementar o sincronizador de arquivos para gerar e manter `.orion/memory/MEMORY.md` formatado em seções limpas.
4. **Passo 4:** Criar as classes `MemorizeTool`, `RecallTool` e `DeprecateFactTool` herdando de `BaseTool` (padrão Pydantic v2 do ORION).
5. **Passo 5:** Conectar as ferramentas ao catálogo do ReAct Engine e testar a invocação dinâmica.
6. **Passo 6:** Escrever testes cobrindo tentativas de *memory poisoning* e validação do limite de 200 linhas do `MEMORY.md`.

---

## 8. Testes Automatizados & Critérios de Aceite (DoD)

### Cenários de Teste Obrigatórios
- **Teste 1:** Um fato `INFERRED` ("Usuário prefere tabs") tenta sobrescrever um fato `CONFIRMED` ("Usuário usa 4 espaços") $\rightarrow$ A operação é bloqueada e o fato confirmado permanece intocado.
- **Teste 2:** Chamada a `memorize(status="CONFIRMED")` atualiza o banco relacional e reflete no arquivo `.orion/memory/MEMORY.md`.
- **Teste 3:** Arquivo `MEMORY.md` gerado nunca ultrapassa 200 linhas; itens excedentes acionam alerta de compactação estruturada.
- **Teste 4:** Ferramenta `recall` chamada pelo modelo retorna payload híbrido RRF em $< 20\text{ ms}$.

### Definition of Done (DoD)
- [ ] Máquina de estados `FactStatus` implementada e blindada contra *memory poisoning*.
- [ ] Ferramentas `memorize`, `recall` e `deprecate_fact` testadas e integradas ao ReAct.
- [ ] `pytest tests/unit/test_facts_store.py tests/unit/test_memory_tools.py` passando com 100% de sucesso.
- [ ] Cobertura de testes dos módulos $\ge 90\%$.
- [ ] Documentação de progresso atualizada em `.claudex/progress.md`.
