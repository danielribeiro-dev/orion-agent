# Sprint — [v0.4.0] Sprint 4: Native MCP Client & Integração PEP

> **Status:** 📋 Planejado  
> **Versão Relacionada:** v0.4.0 (High-Performance Stream CLI, Slash Commands & Native MCP)  
> **Responsável / Agente:** Daniel Dev & Antigravity  
> **Data de Início:** A definir (Fase 4)  
> **Data de Conclusão:** —  

---

## 1. Identificação & Objetivo

* **Objetivo Primário:** Implementar o cliente nativo do **Model Context Protocol (MCP)** no O.R.I.O.N, com suporte aos dois transportes padrão da indústria (**stdio** via subprocesso e **SSE** via HTTP), adaptador dinâmico que converte ferramentas MCP remotas em instâncias de `BaseTool` nativas do ORION, integração determinística com o Policy Enforcement Point (PEP) para controle de permissões e auditoria, e o comando slash `/mcp` para inspeção e gerenciamento de conexões.
* **Dependências Prévias:** Sprints 1, 2 e 3 concluídas (Stream CLI, Prompt Interativo e Slash Commands funcionais).
* **Entregável Verificável:** Pacote `src/orion/mcp/` totalmente operacional, capaz de se conectar a servidores MCP como GitHub MCP, Postgres MCP ou Brave Search MCP através de `~/.orion/mcp_servers.json`, descobrindo ferramentas e executando tool calls sob o crivo de governança do PEP.

---

## 2. Contexto de Engenharia

* **Por que esta sprint existe:** Para garantir que o ORION seja universalmente extensível sem a necessidade de codificar manualmente cada serviço externo no núcleo do projeto. O padrão aberto MCP (criado pela Anthropic e adotado pela indústria) permite conectar bancos de dados, APIs e serviços de terceiros de forma padronizada e segura.
* **Como se encaixa na visão global:** Conclui a v0.4.0, entregando uma interface de terminal hiperprodutiva e uma ponte universal de ferramentas externas com governança militar.
* **Decisões arquiteturais associadas:** ADR-002 (Núcleo Aberto com Integrações Agnósticas), ADR-006 (Governança PEP), ADR-016 (Catálogo de Slash Commands).

---

## 3. Estado Atual vs. Estado Desejado

| Aspecto | Estado Inicial (Antes da Sprint) | Estado Final Esperado (DoD) |
| :--- | :--- | :--- |
| **Integração MCP** | Inexistente | Cliente nativo assíncrono conectando via stdio e SSE |
| **Conversão de Tools** | Apenas as 5 primitivas nativas | Ferramentas MCP expostas dinamicamente no ReAct Engine |
| **Governança de MCP** | Nenhuma | Toda chamada de ferramenta MCP passa pelo PEP e gera log em `audit.log` |
| **Gestão no CLI** | Inexistente | Comando `/mcp` para listar status, ping e ferramentas conectadas |

---

## 4. Escopo da Sprint

### ✅ No Escopo (In Scope)
- [ ] Adicionar dependência `mcp>=1.0.0` (ou implementação leve direta de JSON-RPC 2.0 assíncrona) no `pyproject.toml`.
- [ ] Implementação de `MCPClient` em `src/orion/mcp/client.py`:
  - Leitura de configuração em `~/.orion/mcp_servers.json` e `<workspace>/.orion/mcp_servers.json`.
  - Gerenciamento de ciclo de vida de servidores (inicialização, ping de saúde, reconexão e encerramento).
- [ ] Implementação dos transportes em `src/orion/mcp/transports/`:
  - `StdioTransport`: execução de subprocessos (`npx`, `uvx`, `python`) com comunicação por pipes assíncronos.
  - `SSETransport`: comunicação HTTP com Server-Sent Events para servidores remotos.
- [ ] Implementação de `MCPToolAdapter` em `src/orion/mcp/adapter.py`:
  - Mapeamento de schemas JSON de ferramentas MCP para schemas Pydantic v2 do ORION.
  - Interceptação de cada chamada pelo Policy Enforcement Point (PEP): ferramentas de leitura autorizadas (LEVEL_1), ferramentas mutadoras bloqueadas até confirmação do usuário no modo supervisionado (LEVEL_2).
- [ ] Implementação do comando slash `/mcp` em `src/orion/tui/commands/mcp.py`.
- [ ] Testes unitários com servidores MCP mockados validando descoberta, execução e interceptação de segurança.

### 🚫 Fora de Escopo (Out of Scope / Anti-Metas)
- Não construir servidores MCP próprios nesta versão (apenas cliente receptor).
- Não criar assistente de voz headless (escopo da v0.5.0).

---

## 5. Arquitetura & Arquivos Afetados

```
src/orion/mcp/
├── __init__.py
├── client.py                          # MCPClient gerenciador de múltiplos servidores
├── models.py                          # MCPServerConfig, MCPToolDefinition
├── adapter.py                         # Converte MCP Tool -> Orion BaseTool
├── transports/
│   ├── __init__.py
│   ├── base.py                        # BaseTransport
│   ├── stdio.py                       # Transporte Stdio assíncrono
│   └── sse.py                          # Transporte HTTP SSE
└── commands/mcp.py                    # Implementação do comando /mcp
tests/
└── unit/
    ├── test_mcp_client.py
    ├── test_mcp_adapter.py
    └── test_mcp_pep_security.py
```

---

## 6. Contratos de Código & Tipagem

```python
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

class MCPServerConfig(BaseModel):
    name: str
    command: Optional[str] = None
    args: List[str] = []
    env: Dict[str, str] = {}
    url: Optional[str] = None
    transport: str = "stdio" # "stdio" ou "sse"

class MCPToolDefinition(BaseModel):
    server_name: str
    name: str
    description: str
    input_schema: Dict[str, Any]
```

---

## 7. Estratégia de Implementação (Passo a Passo)

1. **Passo 1:** Definir os contratos Pydantic de configuração e ferramentas MCP em `src/orion/mcp/models.py`.
2. **Passo 2:** Implementar os transportes assíncronos `stdio` e `sse` com tratamento de timeouts e encerramento limpo de processos filhos.
3. **Passo 3:** Desenvolver `MCPClient` para gerenciar a lista de conexões ativas a partir de `mcp_servers.json`.
4. **Passo 4:** Criar `MCPToolAdapter` conectando cada ferramenta remota à máquina de execução do ReAct com validação no PEP.
5. **Passo 5:** Implementar o comando `/mcp` exibindo tabela Rich com servidores, ferramentas ativas e latência.
6. **Passo 6:** Escrever testes de integração com servidor MCP de teste mockado.

---

## 8. Testes Automatizados & Critérios de Aceite (DoD)

### Cenários de Teste Obrigatórios
- **Teste 1:** Conexão stdio inicializa subprocesso, executa handshake JSON-RPC e lista ferramentas em $< 200\text{ ms}$.
- **Teste 2:** Ferramenta MCP mutadora (ex: `delete_record`) é interceptada pelo PEP antes da execução.
- **Teste 3:** Servidor MCP que cai ou trava não congela o CLI principal (timeout e isolamento gracioso).

### Definition of Done (DoD)
- [ ] Cliente MCP nativo implementado para `stdio` e `sse`.
- [ ] Ferramentas MCP convertidas para `BaseTool` e registradas no catálogo do ReAct.
- [ ] Comando `/mcp` funcional no CLI.
- [ ] `pytest tests/unit/test_mcp_client.py tests/unit/test_mcp_pep_security.py` passando com 100% de sucesso.
- [ ] Cobertura de testes dos módulos $\ge 90\%$.
- [ ] Documentação de progresso atualizada em `.claudex/progress.md`.
