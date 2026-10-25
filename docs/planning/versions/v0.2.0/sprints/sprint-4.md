# Sprint — [v0.2.0] Sprint 4: Universal Skills Standard & Dynamic Compactor

> **Status:** 📋 Planejado  
> **Versão Relacionada:** v0.2.0 (Cognitive Continuity: The 5-Sphere Memory, Universal Skills Standard & Dynamic Compaction)  
> **Responsável / Agente:** Daniel Dev & Antigravity  
> **Data de Início:** A definir (Fase 2)  
> **Data de Conclusão:** —  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Implementar o motor do **Universal Agent Skills Standard** (`SKILL.md`) com suporte a **Divulgação Progressiva (*Progressive Disclosure*)**, o **Dynamic Context Compactor** (auto-compaction a 80% do budget de contexto e comando `/compact` com preservação de *vital tail* e arquivos ativos), e o gerenciador de **Branches Contextuais** (`/branch`, `/merge`) com síntese de checkpoints imutáveis na Main Timeline.
* **Dependências Prévias:** Sprints 1, 2 e 3 concluídas (Memória Tríplice e Ferramentas Cognitivas operacionais).
* **Entregável Verificável:** Módulos `src/orion/skills/` e `src/orion/timeline/` totalmente operacionais, permitindo carregar habilidades padronizadas com pegada mínima de tokens, ramificar sessões de trabalho e compactar o histórico dinamicamente sem perda de intenção operacional.

---

## 2. Contexto de Engenharia

* **Por que esta sprint existe:** Para fechar o ciclo de inteligência da v0.2.0 e garantir superioridade estrutural sobre Claude Code e Antigravity:
  1. Habilidades não podem poluir o prompt com milhares de linhas estáticas; precisam seguir o padrão de mercado `SKILL.md` com carregamento sob demanda.
  2. Sem compactador dinâmico, qualquer tarefa longa de engenharia de software esgota a janela de contexto ou estoura a fatura de tokens.
  3. Sem branches contextuais, investigações de depuração geram ruído permanente na timeline principal.
* **Como se encaixa na visão global:** Conclui a v0.2.0, entregando uma plataforma com continuidade cognitiva perpétua, habilidades modulares interoperáveis e saúde contínua da janela de contexto.
* **Decisões arquiteturais associadas:** ADR-010 (Padrão Universal Agent Skills), ADR-011 (Dynamic Context Compactor).

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Estado Inicial (Antes da Sprint) | Estado Final Esperado (DoD) |
| :--- | :--- | :--- |
| **Habilidades** | Inexistentes | Carregador dinâmico compatível com `SKILL.md` (Workspace > Global > Builtin) |
| **Startup Prompt** | Sem skills | Injeção de apenas `name` e `description` no bloco `<AVAILABLE_SKILLS>` (<100 tok/skill) |
| **Janela Longa** | Falha ou estouro de contexto | Dynamic Compactor reduz o histórico preservando *vital tail* e arquivos ativos |
| **Sessões Isoladas** | Todas no mesmo fluxo | Ramificações `/branch <nome>` com merge sintetizado na Main Timeline |

---

## 4. Escopo da Sprint

### ✅ No Escopo (In Scope)
- [ ] Implementação do Padrão Universal `Agent Skills` em `src/orion/skills/`:
  - `models.py`: Modelos Pydantic v2 `SkillMetadata` e `SkillBundle`.
  - `loader.py`: Scanner hierárquico com precedência (`<workspace>/.orion/skills/` $\rightarrow$ `~/.orion/skills/` $\rightarrow$ `src/orion/builtin/skills/`).
  - `engine.py`: Gerador do bloco conciso `<AVAILABLE_SKILLS>` e ferramenta nativa `use_skill(skill_name)`.
- [ ] Implementação do `Dynamic Context Compactor` em `src/orion/timeline/compactor.py`:
  - Disparo automático quando o uso da janela atinge 80% do limite máximo.
  - Comando slash manual `/compact` (com suporte a foco direcional).
  - Algoritmo de redução: sumariza raciocínio e etapas concluídas, descarta saídas intermediárias de ferramentas volumosas, preserva intactos os últimos 3 a 5 turnos (*vital tail*), os caminhos dos arquivos modificados e os artefatos ativos.
  - Notificação visual elegante no stream da TUI.
- [ ] Implementação de `BranchManager` em `src/orion/timeline/branch_manager.py`:
  - Isolamento de histórico em branches (`/branch refactor-auth`).
  - Algoritmo de síntese no `/merge`: sintetiza 3 a 5 linhas executivas e publica como checkpoint na Main Timeline.
  - Arquivamento dos logs detalhados em `~/.orion/timeline/archive/`.
- [ ] Criação da skill de sistema inicial `system-doctor` em `src/orion/builtin/skills/system-doctor/SKILL.md` para auto-auditoria de ambiente.
- [ ] Testes unitários e de integração simulando sessões longas com compactação e merge de branches.

### 🚫 Fora de Escopo (Out of Scope / Anti-Metas)
- Não construir a interface TUI completa em Rich com streaming e diffs (escopo da v0.4.0).
- Não plugar clientes MCP remotos (escopo da v0.4.0).
- Não criar assistente de voz headless (escopo da v0.5.0).

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/
├── skills/
│   ├── __init__.py
│   ├── models.py                      # SkillMetadata, SkillBundle
│   ├── loader.py                      # Carregador hierárquico de skills
│   └── engine.py                      # Progressive Disclosure & use_skill tool
├── timeline/
│   ├── __init__.py
│   ├── compactor.py                   # Context Compactor (80% threshold + /compact)
│   ├── branch_manager.py              # Controle de branches contextuais
│   └── checkpoint_synthesis.py        # Síntese executiva de checkpoint
└── builtin/
    └── skills/
        └── system-doctor/
            └── SKILL.md               # Skill nativa de diagnóstico
tests/
└── unit/
    ├── test_skills_loader.py          # Testes de parsing e progressive disclosure
    ├── test_compactor.py              # Testes de compactação sem perda de estado
    └── test_branches.py               # Testes de isolamento e síntese de branch
```

---

## 6. Contratos de Código & Tipagem

```python
import re
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator

class SkillMetadata(BaseModel):
    name: str = Field(..., max_length=64)
    description: str = Field(..., max_length=1024)
    license: Optional[str] = None
    compatibility: Optional[str] = None
    allowed_tools: Optional[List[str]] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", v):
            raise ValueError("O nome da skill deve conter apenas minúsculas, números e hífens simples")
        return v

class CompactionResult(BaseModel):
    original_turns: int
    compacted_summary: str
    preserved_tail_turns: int
    active_files: List[str]
    tokens_saved: int
```

---

## 7. Estratégia de Implementação (Passo a Passo)

1. **Passo 1:** Definir os contratos Pydantic para metadados de habilidades em `src/orion/skills/models.py`.
2. **Passo 2:** Desenvolver o parser e scanner hierárquico de diretórios em `src/orion/skills/loader.py`.
3. **Passo 3:** Implementar o motor de divulgação progressiva e a ferramenta `use_skill` em `src/orion/skills/engine.py`.
4. **Passo 4:** Implementar o `Dynamic Context Compactor` em `src/orion/timeline/compactor.py` com preservação de estado ativo e *vital tail*.
5. **Passo 5:** Implementar o `BranchManager` e a rotina de síntese de checkpoints para unificação com a Main Timeline.
6. **Passo 6:** Criar a skill built-in `system-doctor` demonstrando o uso prático de instruções e scripts auxiliares.
7. **Passo 7:** Escrever testes cobrindo parsing de YAML frontmatter, regras de nomes inválidos, testes de compactação e merges de branch.

---

## 8. Testes Automatizados & Critérios de Aceite (DoD)

### Cenários de Teste Obrigatórios
- **Teste 1:** Scanner varre 10 skills e consome menos de 800 tokens no bloco `<AVAILABLE_SKILLS>`.
- **Teste 2:** Ativação de skill via `use_skill` carrega as instruções do `SKILL.md` correspondente no turno imediato.
- **Teste 3:** Dynamic Compactor acionado em histórico com 40 turnos reduz o tamanho total em pelo menos 60%, mantendo intactos os 3 turnos finais literais e a lista de arquivos modificados.
- **Teste 4:** Merge de branch gera resumo executivo de 3 a 5 linhas na Main Timeline e arquiva o log detalhado em disco.

### Definition of Done (DoD)
- [ ] Universal Agent Skills Standard plenamente funcional e aderente às especificações de mercado.
- [ ] Dynamic Context Compactor testado com e sem foco direcional.
- [ ] Isolamento de branches contextuais validado.
- [ ] `pytest tests/unit/test_skills_loader.py tests/unit/test_compactor.py tests/unit/test_branches.py` passando com 100% de sucesso.
- [ ] Cobertura de testes dos módulos $\ge 90\%$.
- [ ] Documentação de progresso atualizada em `.claudex/progress.md`.
