# O.R.I.O.N — System Patterns & Invariantes de Arquitetura
*(Operational Reasoning & Intelligence Orchestration Network)*

Este documento estabelece as **regras imutáveis de engenharia** do `orion-agent`. Todo desenvolvedor ou agente de IA que trabalhar nesta base de código deve respeitar estes padrões sem exceção.

---

## 1. Princípios Fundamentais

1. **Separação Cérebro × Corpo (Brain × Body)**:
   - O núcleo cognitivo (`orion.core`) nunca executa chamadas diretas de I/O de baixo nível (`os.system`, `subprocess.Popen`, manipulação crua de sockets ou arquivos fora de contratos).
   - Toda execução física no sistema operacional passa obrigatoriamente pelo `LocalRuntimeProvider` e pelas 5 ferramentas primitivas.
2. **Nenhuma Ação sem Governança Determinística (Policy Enforcement Point - PEP)**:
   - Nenhuma ferramenta mutante de sistema (gravar arquivo, executar script, abrir porta de rede, matar processo) pode ser disparada sem passar pela validação determinística do PEP.
   - O PEP opera com "Deny by Default" e 4 níveis estritos (`LEVEL_0` a `LEVEL_3`).
3. **Padrão Action-Observation Event Stream**:
   - Todo o loop cognitivo do agente emite instâncias imutáveis de `Action` e processa retornos encapsulados em `Observation` via `EventBus`.
   - Limite estrito de turn budgeting (teto máximo de 20 passos por tarefa).
4. **Soberania das 5 Ferramentas Primitivas Nativas**:
   - As 5 ferramentas fundamentais (`run_command`, `read_file`, `write_file`, `edit_file`, `search_files`) vivem nativamente no núcleo do ORION com implementação pura e independente de agentes externos.
   - `edit_file` utiliza substituição exata por correspondência ancorada de bloco (`exact string target replacement`) com verificação de unicidade.
5. **Subsistema de Artefatos Estruturados**:
   - Planos técnicos, relatórios de auditoria e análises densas são emitidos como artefatos markdown estruturados com metadados (`RequestFeedback`, `Summary`, `UserFacing`) com persistência dual (`~/.orion/brain/` global e `.orion/artifacts/` local).
6. **Consciência de Custos & Dynamic Auto-Routing**:
   - Observabilidade de tokens e custos em USD/BRL exibida de forma concisa no CLI.
   - Suporte aos modos `auto` (chaveamento dinâmico de complexidade de raciocínio vs execução rápida) e `fixed` (modelo fixo do usuário), configuráveis por `/config` ou linguagem natural.
7. **Memória Tríplice em Camadas Especializadas (v0.2.0)**:
   - Eventos temporais vivem em SQLite com FTS5 (busca léxica BM25 exata).
   - Semântica e conceitos vivem em Vector Store local (ONNX/FastEmbed).
   - Fatos imutáveis e perfis vivem em formato estruturado (JSON/SQLite tabular).
8. **Dados de Runtime Isolados do Código**:
   - Todo dado gerado em tempo de execução (bancos de dados, logs, métricas, sockets Unix) vive em `~/.orion/` no diretório do usuário, **NUNCA** dentro da pasta do código-fonte do repositório.

---

## 2. Padrões de Código e Tipagem

- **Linguagem:** Python 3.11+
- **Tipagem Estrita:** Uso de `typing` e Pydantic v2 para todos os modelos de dados, configurações e contratos de payload.
- **Assincronismo Nativo:** Todo o loop de orquestração, streaming de respostas, eventos e execução de processos são implementados com `asyncio`.
- **Zero SQL Injection:** Todas as operações em SQLite utilizam queries parametrizadas com placeholders `?`.
- **Tratamento Limpo de Erros:** Erros de provedores e ferramentas são capturados, tratados e traduzidos para tipos de exceção do domínio do ORION, evitando que stack traces vazem para o usuário final sem explicação legível.
