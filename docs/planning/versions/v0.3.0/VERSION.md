# Spec — [v0.3.0] Model Gateway, Real-Time Cost Ledger & Offline Resilience ("ORION Imortal")

> **Status:** 📋 Especificação Formalizada e Congelada para Execução após a v0.2.0  
> **Criada em:** 2026-10-25  
> **Concluída em:** —  
> **Autor(es):** Daniel Dev & Antigravity (Pair Programming)  
> **Branch:** `version/v0.3.0`  

---

## 1. Visão Geral & Motivação

### 1.1 Objetivo
Construir a camada de **Inteligência de Modelos, Soberania Econômica e Resiliência Operacional Contínua** do **O.R.I.O.N (Operational Reasoning & Intelligence Orchestration Network)**, entregando:
1. **Model Gateway com Prioridade OpenRouter:** Abstração agnóstica de provedores (`BaseLLMProvider`), estabelecendo o OpenRouter como hub unificado primário com acesso a múltiplos modelos de ponta com uma única credencial, além de arquitetura aberta para provedores diretos.
2. **Dynamic Auto-Routing por Complexidade:** Classificador inteligente de carga cognitiva por turno (tiers: *Fast/Lite*, *Balanced*, *Heavy Frontier*), alternando modelos de ponta para arquitetura e modelos rápidos/econômicos para comandos rotineiros, otimizando custos em até 70% com precisão de 98%+.
3. **Livro-Razão de Custos em Tempo Real (`metrics.db`):** Banco local SQLite WAL rastreando tokens de entrada, saída e cache, calculando gastos em USD e BRL em tempo real e aplicando limites orçamentários (*Daily Budget Cap*).
4. **"ORION Imortal" (Failover Offline Ultrarrápido):** Circuit breaker com monitoramento de latência e falhas de rede, executando chaveamento automático em menos de 2 segundos para inferência local via Ollama utilizando a família leve **`qwen2.5-coder:1.5b`** ou **`qwen2.5-coder:3b`** (~1.5GB a 2.8GB de RAM), garantindo operação ininterrupta mesmo sem internet.
5. **Autonomia Adaptativa & Nuclear Step-Up Auth no PEP:** 
   - *Command Trust Ledger:* Cache de padrões de comandos seguros e conhecidos (inclusive `sudo` não-destrutivos como `apt install`); solicita confirmação na primeira vez e roda silenciosamente em modo auto nas subsequentes.
   - *Nuclear Threshold com Popup Obrigatório do SO:* Operações de alto impacto ou raio de destruição catastrófico disparam incondicionalmente um popup nativo de senha/biometria do sistema operacional (Polkit/`pkexec` ou `zenity`), exigindo presença física deliberada do usuário em qualquer modo.

### 1.2 Por que agora?
Após a estruturação do Core ReAct Engine (v0.1.0) e da Memória Tríplice Contínua (v0.2.0), o ORION precisa de inteligência de seleção de modelos, independência de fornecedor único (superando o Claude Code, que é amarrado à Anthropic) e proteção física contra destruição antes de receber a interface completa de terminal Stream CLI (v0.4.0) e o modo de voz ambiente (v0.5.0).

### 1.3 O que NÃO é escopo (anti-metas)
- Não construir a interface TUI em `prompt_toolkit` com autocomplete `/` e `@` (escopo da v0.4.0).
- Não plugar microfone ou síntese de voz nativa (escopo da v0.5.0).
- Não criar sandbox de contêineres Bubblewrap (escopo da v1.5.0).

---

## 2. Decisões Arquiteturais & Diretrizes de Design (ADRs)

- **ADR-009:** Dynamic Auto-Routing de Modelos por Complexidade & Ledger no CLI.
- **ADR-017:** Command Trust Ledger & Autonomia Adaptativa (Capability Caching).
- **ADR-018:** Nuclear Threshold & Popup Obrigatório de Senha do SO (Step-Up Authentication).
- **ADR-019:** Gateway de Modelos com Foco em OpenRouter & Failover Local Leve (Qwen Coder 1.5B/3B).

---

## 3. Divisão em Sprints & Entregáveis

| Sprint | Nome da Sprint | Objetivo Principal | Documento | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Sprint 1** | Model Registry & OpenRouter Provider | Contrato abstrato `BaseLLMProvider`, integração completa do OpenRouter com streaming e tipagem de tokens | [`sprints/sprint-1.md`](sprints/sprint-1.md) | 📋 Planejado |
| **Sprint 2** | Dynamic Auto-Routing & Complexity Engine | Motor classificador de complexidade de turno (Fast/Lite, Balanced, Heavy) e modos `auto` vs `fixed` | [`sprints/sprint-2.md`](sprints/sprint-2.md) | 📋 Planejado |
| **Sprint 3** | Real-Time Multi-Currency Cost Ledger & Budgeting | Livro-razão em SQLite WAL (`metrics.db`), rastreamento de custos em USD/BRL e tetos orçamentários | [`sprints/sprint-3.md`](sprints/sprint-3.md) | 📋 Planejado |
| **Sprint 4** | ORION Imortal (Failover Local) & Nuclear Step-Up Auth | Circuit breaker para failover local < 2s (Qwen Coder 1.5B/3B no Ollama) + Command Trust Ledger e Popup do SO | [`sprints/sprint-4.md`](sprints/sprint-4.md) | 📋 Planejado |

---

## 4. Arquitetura Alvo & Componentes Afetados

```
src/orion/
├── gateway/
│   ├── __init__.py
│   ├── models.py                      # LLMRequest, LLMResponse, ModelInfo, ComplexityLevel
│   ├── router.py                      # Dynamic Auto-Routing (Fast/Lite vs Balanced vs Heavy)
│   ├── ledger.py                      # Livro-razão SQLite WAL em ~/.orion/metrics.db
│   ├── budget.py                      # Gestor de limites orçamentários diários (USD/BRL)
│   ├── circuit_breaker.py             # Circuit breaker de rede e failover para Ollama (< 2s)
│   └── providers/
│       ├── __init__.py
│       ├── base.py                    # BaseLLMProvider com streaming unificado
│       ├── openrouter.py              # Provedor prioritário de primeira classe
│       └── local_ollama.py            # Adaptador local para qwen2.5-coder:1.5b / 3b
└── governance/
    ├── trust_ledger.py                # CommandTrustLedger (cache de comandos conhecidos/seguros)
    └── nuclear.py                     # Nuclear Threshold & OS Step-Up Auth Popup (Polkit/Zenity/PAM)
```

---

## 5. Matriz de Critérios de Aceite da Versão (DoD Global)

| ID | Cenário | Comportamento Esperado | Como Validar | Status |
|:---|:---|:---|:---|:---|
| CA-01 | Integração OpenRouter | Requisições fluem com streaming assíncrono e contagem precisa de tokens | `pytest tests/unit/test_openrouter.py` | ⏳ Pendente |
| CA-02 | Dynamic Auto-Routing | Tarefas simples são roteadas para modelo rápido; tarefas de arquitetura para modelo de topo | `pytest tests/unit/test_router.py` | ⏳ Pendente |
| CA-03 | Livro-Razão & Custos | Registros persistidos em `metrics.db` com cálculo em USD e conversão para BRL | `pytest tests/unit/test_ledger.py` | ⏳ Pendente |
| CA-04 | ORION Imortal (Failover < 2s) | Em caso de timeout/falha de rede na nuvem, chaveia para Ollama local em $< 2$ segundos | `pytest tests/unit/test_circuit_breaker.py` | ⏳ Pendente |
| CA-05 | Command Trust Ledger | Comandos conhecidos e já autorizados rodam sem confirmação em modo auto | `pytest tests/unit/test_trust_ledger.py` | ⏳ Pendente |
| CA-06 | Nuclear Step-Up Auth Popup | Comandos destrutivos invocam popup de senha do SO mesmo em modo auto | `pytest tests/unit/test_nuclear.py` | ⏳ Pendente |

---

## 6. Checklist de Conclusão da Spec (Congelamento)

- [ ] Todos os critérios de aceite validados por suíte de testes.
- [ ] Cobertura de testes unitários $\ge 85\%$ em `src/orion/gateway/` e módulos de governança.
- [ ] Documentação e registros de decisão alinhados em `.claudex/`.
- [ ] Commit e tag no Git.
