# ORION-Agent — Governança e Policy Enforcement Point (PEP)

> Especificação do sistema determinístico de segurança, permissões e níveis de autonomia do ORION.

---

## 1. O Princípio de Deny by Default

O ORION opera sob o princípio do privilégio mínimo:
- Nenhum modelo de IA tem autorização intrínseca para executar comandos ou alterar arquivos.
- Toda intenção de ação emitida pelo modelo deve ser interceptada pelo **Policy Enforcement Point (PEP)** antes que qualquer código seja executado no sistema.

---

## 2. Níveis de Ação (Action Levels)

Cada ferramenta registrada no ORION possui uma classificação estática de risco:

| Nível | Categoria | Descrição | Comportamento Padrão |
| :--- | :--- | :--- | :--- |
| **LEVEL 0** | Informativo | Consulta de dados em memória, respostas de texto, raciocínio interno. | Execução direta imediata. |
| **LEVEL 1** | Leitura Passiva | Leitura de arquivos locais, busca na web, status do sistema operacional. | Execução direta com log de auditoria. |
| **LEVEL 2** | Mutante de Baixo Risco | Criação ou edição de arquivos de projeto dentro do workspace atual. | Confirmação explícita no Modo Supervisionado. |
| **LEVEL 3** | Crítico de Sistema | Comandos shell arbitrários, exclusão de arquivos, desligamento, alteração de configurações de rede. | Confirmação explícita com exibição de diff/impacto. |

---

## 3. Níveis de Autonomia Configuráveis

O usuário pode alternar o nível de autonomia do ORION de forma global ou por sessão através do comando `/config`:

1. **Modo Supervisionado (Padrão no MVP):**
   - Ações de Nível 2 e 3 sempre exibem prompt de autorização `[Y/n]` no terminal ou por voz antes de disparar.
2. **Modo Workspace Autônomo:**
   - Ações de Nível 2 dentro da pasta do projeto atual rodam sem confirmação. Ações de Nível 3 (fora do workspace ou comandos de risco) continuam exigindo confirmação.
3. **Modo Totalmente Autônomo (Com Limites Rígidos):**
   - O agente tem autonomia para executar planos completos, mas com travas invioláveis:
     - Impossível executar comandos com `sudo` sem autorização humana.
     - Impossível alterar arquivos fora do diretório autorizado do usuário.
     - Impossível encerrar o próprio processo do ORION (*Self-kill protection*).

---

## 4. Auditoria e Rastreabilidade

Todas as ações sensíveis são gravadas de forma append-only no arquivo `~/.orion/audit.log`, contendo:
- `timestamp`: Momento exato da execução.
- `tool`: Nome da ferramenta acionada.
- `params`: Parâmetros enviados.
- `user_authorized`: Se houve confirmação humana ou se rodou por política autônoma.
- `result_status`: Sucesso ou falha com código de saída.
