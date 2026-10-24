# ORION-Agent — Arquitetura da Memória Tríplice

> Especificação técnica detalhada dos três mecanismos coordenados de armazenamento, recuperação híbrida via RRF e governança cognitiva do O.R.I.O.N.

---

## 1. O Problema da Dependência Vetorial Exclusiva

A maioria das soluções de agentes modernas sofre de falhas graves ao utilizar apenas bancos vetoriais:
- **Perda de Contexto Temporal:** Embeddings não entendem naturalmente "ontem", "semana passada" ou a ordem cronológica estrita dos acontecimentos.
- **Similaridade Falsa:** Duas frases com vocabulário parecido recebem alta similaridade mesmo que uma trate de um fato descartado e a outra de uma regra vigente.
- **Incapacidade de Buscar Termos Exatos:** Erros de compilação, hashes de commit, nomes de variáveis ou comandos específicos muitas vezes são perdidos em buscas semânticas puras.
- **Envenenamento de Memória (*Memory Poisoning*):** Hipóteses provisórias ou erros investigados pelo modelo acabam gravados no banco vetorial como "verdades", corrompendo decisões futuras.

---

## 2. A Solução: Memória Tríplice Coordenada

```
┌────────────────────────────────────────────────────────────────────────┐
│                        ORION Memory Orchestrator                       │
├──────────────────┬──────────────────────┬──────────────────────────────┤
│ 1. Linha do Tempo│ 2. Memória Semântica │ 3. Memória Estruturada       │
│    e Eventos     │    e Conceitual      │    de Fatos e Decisões       │
├──────────────────┼──────────────────────┼──────────────────────────────┤
│ SQLite WAL + FTS5│ ONNX / FastEmbed     │ SQLite Relacional / Pydantic │
│ (Léxico / BM25)  │ (Similaridade Cosseno│ (Chave-Valor Tipado          │
│ Sub-10ms latency │  Local e Offline)    │  com Ciclo de Certeza)       │
└──────────────────┴──────────────────────┴──────────────────────────────┘
```

### Camada 1: Linha do Tempo e Histórico de Eventos (Episódica Temporal)
- **Engine:** SQLite 3 configurado em modo WAL (`PRAGMA journal_mode=WAL;`) com tabela virtual FTS5 (`porter unicode61`).
- **Arquivo Físico:** `~/.orion/timeline.db`.
- **Conteúdo:** Todas as interações, execuções de comandos, notificações do sistema, Day Markers (`DayMarker: YYYY-MM-DD`) e resumos periódicos.
- **Recuperação:** Ordenação cronológica estrita combinada com busca de termos exatos (BM25), respondendo em $< 10\text{ ms}$.

### Camada 2: Memória Semântica e Conceitual (Conhecimento Amplo)
- **Engine:** `fastembed` executando em CPU ou GPU local via ONNX Runtime (zero dependência de PyTorch pesado).
- **Modelo Padrão Homologado:** `bge-small-en-v1.5` (384 dimensões, pegada de disco $< 130\text{ MB}$, altíssima precisão para terminologia técnica e código).
- **Conteúdo:** Insights consolidados, arquitetura de sistemas, causas-raiz de bugs complexos e analogias funcionais.
- **Deduplicação Inteligente:** Se um novo item possui similaridade de cosseno $\ge 0.92$ com uma memória já existente, o sistema não duplica a entrada: ele atualiza a pontuação de relevância e o timestamp da existente.

### Camada 3: Memória Estruturada de Fatos e Decisões
- **Engine:** Tabelas relacionais em SQLite com validação via esquemas Pydantic v2.
- **Conteúdo:**
  - Perfil do usuário (nome, timezone, linguagens preferidas, convenções).
  - Decisões de Arquitetura (ADRs locais do usuário e preferências operacionais).
- **Máquina de Estados de Certeza (Prevenção de *Memory Poisoning*):**
  ```mermaid
  stateDiagram-v2
      [*] --> INFERRED: Agente detecta padrão ou hipótese
      INFERRED --> CONFIRMED: Usuário confirma explicitamente ou instrui no chat
      INFERRED --> DEPRECATED: Hipótese refutada por erro ou evidência
      CONFIRMED --> DEPRECATED: Usuário revoga regra antiga ou decide mudar padrão
      DEPRECATED --> [*]
  ```
  - `CONFIRMED`: Informação explícita autorizada pelo usuário. Tem prioridade máxima e nunca é descartada por inferência.
  - `INFERRED`: Hipótese observada pelo agente aguardando validação ou recorrência. Nunca substitui um fato confirmado.
  - `DEPRECATED`: Fato ou convenção antiga formalmente revogada. Permanece no histórico para evitar que o agente volte a cometer o mesmo erro superado.

---

## 3. Persistência em Arquivo: Índice Curado & Logs Diários

Para permitir auditoria humana direta e compatibilidade com o fluxo do desenvolvedor (inspirado no padrão do Claude Code e OpenHands), o ORION sincroniza sua memória em arquivos no disco:

```text
.orion/memory/ (ou ~/.orion/memory/)
├── MEMORY.md                 # Índice curado de alta relevância (teto de 200 linhas)
└── daily/
    ├── 2026-10-24.md         # Notas de trabalho e decisões do dia
    └── 2026-10-25.md
```

- **`MEMORY.md` (Curated Index Pointer):** Arquivo de leitura rápida injetado no boot. Possui um teto rígido de 200 linhas. Informações antigas são compactadas ou movidas para arquivos de tópico especializados.
- **Daily Logs (`daily/YYYY-MM-DD.md`):** Histórico de trabalho cronológico do dia, nunca injetado na íntegra no prompt, mas plenamente consultável via busca híbrida.

---

## 4. Recuperação Híbrida e Algoritmo RRF (Reciprocal Rank Fusion)

Quando o usuário faz uma solicitação, o recuperador não confia em uma única técnica:

```mermaid
flowchart LR
    UserQuery[Prompt do Usuário] --> FTS[Busca BM25 no FTS5]
    UserQuery --> VEC[Busca Cosseno no FastEmbed]
    UserQuery --> KB[Busca Chave-Valor em Fatos CONFIRMED]

    FTS --> RRF[RRF Ranker: 1 / (k + rank)]
    VEC --> RRF
    KB --> Prio[Prioridade Absoluta Determinística]

    Prio --> Merger[Context Budget Assembler]
    RRF --> Merger
    Merger --> FinalPayload[Payload Final Injetado < 1500 Tokens]
```

O algoritmo **Reciprocal Rank Fusion (RRF)** combina as posições ranqueadas dos resultados léxicos e semânticos:

$$RRF(d) = \sum_{m \in M} \frac{1}{k + r_m(d)}$$

Onde $k = 60$ (constante empírica padrão), $M$ é o conjunto de métodos de busca (BM25 e Cosseno) e $r_m(d)$ é a posição do documento no método $m$.

### Teto Orçamentário Estrito
O resultado consolidado passa por um truncamento orçamentário rígido:
- **Teto Máximo:** 1.500 tokens.
- Fatos `CONFIRMED` entram com prioridade máxima.
- Os melhores itens do ranking RRF preenchem o espaço restante.
- Isso impede que a recuperação contamine a janela de contexto do raciocínio principal.

---

## 5. Ferramentas Cognitivas Nativas no ReAct Loop

O agente interage com a sua memória através de 3 ferramentas cognitivas primitivas expostas no ReAct loop:

### 5.1 `memorize`
- **Assinatura:** `memorize(key: str, value: str, category: str, status: FactStatus = INFERRED) -> RuntimeResult`
- **Uso:** Gravar uma regra, convenção ou aprendizado. Se o usuário forneceu a informação explicitamente, o status é gravado como `CONFIRMED`.

### 5.2 `recall`
- **Assinatura:** `recall(query: str, mode: str = "hybrid", limit: int = 5) -> RuntimeResult`
- **Uso:** Consultar profundamente a linha do tempo ou histórico antigo quando o prompt imediato não possui dados suficientes.

### 5.3 `deprecate_fact`
- **Assinatura:** `deprecate_fact(key: str, reason: str) -> RuntimeResult`
- **Uso:** Marcar formalmente uma decisão ou regra anterior como superada, impedindo sua reutilização inadvertida.
