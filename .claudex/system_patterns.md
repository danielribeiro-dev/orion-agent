# ORION-Agent — System Patterns & Invariantes de Arquitetura

Este documento estabelece as **regras imutáveis de engenharia** do `orion-agent`. Todo desenvolvedor ou agente de IA que trabalhar nesta base de código deve respeitar estes padrões sem exceção.

---

## 1. Princípios Fundamentais

1. **Separação Cérebro × Corpo (Brain × Body)**:
   - O núcleo de inteligência e planejamento (`orion.core`) nunca executa chamadas diretas de I/O de baixo nível (`os.system`, `subprocess.Popen`, manipulação crua de sockets ou arquivos fora de contratos).
   - Toda execução física no sistema operacional passa obrigatoriamente pelo `RuntimeProvider`.
2. **Nenhuma Ação sem Governança (Policy Enforcement Point)**:
   - Nenhuma ferramenta mutante de sistema (gravar arquivo, executar script, abrir porta de rede, matar processo) pode ser disparada sem passar pela validação determinística do PEP.
   - O PEP opera com "Deny by Default" e respeita o nível de autonomia configurado pelo usuário.
3. **Memória Tríplice em Camadas Especializadas**:
   - Nunca confie exclusivamente em banco vetorial para fatos exatos ou históricos temporais.
   - Eventos temporais vivem em SQLite com FTS5 (busca léxica BM25 exata).
   - Semântica e conceitos vivem em Vector Store local (ONNX/FastEmbed).
   - Fatos imutáveis e perfis vivem em formato estruturado (JSON/SQLite tabular).
4. **Continuidade de Linha do Tempo (Single Timeline Architecture)**:
   - A sessão do ORION é contínua e persistente.
   - Tarefas complexas criam branches contextuais temporárias. Ao término, os aprendizados são sintetizados e gravados na linha principal (*Checkpoint Synthesis*).
5. **Independência de Provedores e Acompanhamento de Custos**:
   - Nenhum modelo proprietário tem monopólio sobre o sistema.
   - O Gateway de Modelos normaliza chamadas e rastreia o consumo de tokens e custos em USD/BRL por tarefa.
6. **Desacoplamento do Hermes e Ferramentas Externas**:
   - O Hermes Agent é temporário e estritamente isolado atrás do `RuntimeProvider`. Nenhuma classe interna de inteligência do Hermes pode ser importada.
   - O padrão nativo e futuro de ferramentas externas do ORION é o **Model Context Protocol (MCP)**.
7. **Dados de Runtime Isolados do Código**:
   - Todo dado gerado em tempo de execução (bancos de dados, logs, sockets Unix, áudio de cache) vive em `~/.orion/` no diretório do usuário, **NUNCA** dentro da pasta do código-fonte do repositório.

---

## 2. Padrões de Código e Tipagem

- **Linguagem:** Python 3.11+
- **Tipagem Estrita:** Uso de `typing` e Pydantic v2 para todos os modelos de dados e contratos de payload.
- **Assincronismo Nativo:** Todo o loop de orquestração, streaming de respostas, eventos e clientes MCP devem ser implementados com `asyncio`.
- **Zero SQL Injection:** Todas as operações em SQLite utilizam queries parametrizadas com placeholders `?` ou bibliotecas seguras.
- **Tratamento Limpo de Erros:** Erros de provedores e ferramentas são capturados, tratados e traduzidos para tipos de exceção do domínio do ORION, evitando que stack traces vazem para o usuário final sem explicação legível.
