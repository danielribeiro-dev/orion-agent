# ORION-Agent — Arquitetura da Memória Tríplice

> Especificação dos três mecanismos coordenados de armazenamento e recuperação inteligente de informações do ORION.

---

## 1. O Problema da Dependência Vetorial Exclusiva

A maioria das soluções de IA modernas sofre de falhas graves ao utilizar apenas bancos vetoriais:
- **Perda de Contexto Temporal:** Embeddings não entendem naturalmente "ontem", "semana passada" ou a sequência cronológica dos eventos.
- **Similaridade Falsa:** Duas frases com vocabulário parecido recebem alta similaridade mesmo que uma trate de um fato descartado e a outra de uma regra vigente.
- **Incapacidade de Buscar Termos Exatos:** Erros de compilação, hashes de commit, nomes de variáveis ou comandos específicos muitas vezes são perdidos em buscas semânticas puras.

---

## 2. A Solução: Memória Tríplice

```
┌────────────────────────────────────────────────────────────────────────┐
│                        ORION Memory Orchestrator                       │
├──────────────────┬──────────────────────┬──────────────────────────────┤
│ 1. Linha do Tempo│ 2. Memória Semântica │ 3. Memória Estruturada       │
│    e Eventos     │    e Conceitual      │    de Fatos e Decisões       │
├──────────────────┼──────────────────────┼──────────────────────────────┤
│ SQLite WAL + FTS5│ ONNX / FastEmbed     │ JSON Schema / SQLite         │
│ (Léxico / BM25)  │ (Similaridade Cosseno│ (Chave-Valor Tipado          │
│                  │  Local e Offline)    │  com Grau de Certeza)        │
└──────────────────┴──────────────────────┴──────────────────────────────┘
```

### Camada 1: Linha do Tempo e Histórico de Eventos (Episódica Temporal)
- **Engine:** SQLite configurado em modo WAL com tabela virtual FTS5.
- **Conteúdo:** Todas as interações, execuções de comandos, notificações do sistema e resumos periódicos.
- **Recuperação:** Ordenação cronológica estrita combinada com busca de termos exatos (BM25).

### Camada 2: Memória Semântica e Conceitual (Conhecimento Amplo)
- **Engine:** FastEmbed / ONNX Runtime local executando modelos como `all-MiniLM-L6-v2` ou `bge-small-en-v1.5`.
- **Conteúdo:** Insights aprendidos, resumos de erros investigados e soluções de arquitetura.
- **Deduplicação Inteligente:** Se um novo item possui similaridade $\ge 0.92$ com uma memória existente, o sistema não cria duplicata: ele atualiza a pontuação de relevância e o timestamp da existente.

### Camada 3: Memória Estruturada de Fatos e Decisões
- **Engine:** SQLite relacional / Pydantic Models serializados.
- **Conteúdo:**
  - Perfil do usuário (nome, fuso horário, linguagens e frameworks preferidos).
  - Decisões de Arquitetura (ADRs locais do usuário e preferências operacionais).
  - Estado de certeza de cada fato:
    - `CONFIRMED`: Informação explícita fornecida pelo usuário.
    - `INFERRED`: Hipótese observada pelo agente aguardando validação.
    - `DEPRECATED`: Fato antigo que foi revogado ou alterado.

---

## 3. Recuperação Híbrida e Montagem de Contexto

Quando o usuário faz uma solicitação, o recuperador:
1. Extrai entidades-chave e busca fatos confirmados na **Memória Estruturada**.
2. Realiza busca híbrida:
   - BM25 no FTS5 da **Linha do Tempo** para capturar termos exatos e eventos recentes.
   - Cosseno no **Vector Store** para capturar analogias semânticas.
3. Ranquear via algoritmo RRF (Reciprocal Rank Fusion).
4. O resultado compacto (máximo de 1.500 tokens) é injetado no prompt sem sobrecarregar a janela de contexto.
