---
name: system-doctor
description: Diagnóstico de saúde do sistema operacional, verificação de recursos de hardware e integridade de ambiente.
license: Apache-2.0
compatibility: linux, macos
allowed_tools:
  - run_command
  - inspect_environment
---

# 🩺 System Doctor — Diagnóstico e Sanidade de Ambiente

O **System Doctor** é a habilidade oficial de auditoria operacional do O.R.I.O.N. Ele guia o agente na execução de verificações determinísticas de saúde de hardware, processos e diretórios críticos.

## 🛠️ Procedimento Operacional Padrão (SOP)

Ao ativar o `system-doctor`, execute o seguinte roteiro de auditoria:

### 1. Telemetria de Hardware (Sphere 3)
Invoque a ferramenta `inspect_environment` para aferir:
- RAM livre e total (garantir conformidade com o *Headroom Guard* de $\ge 1.5\text{ GB}$).
- Carga de CPU (1 minuto).
- Servidor de exibição (`wayland`, `x11` ou `headless`).

### 2. Auditoria de Disco e Armazenamento
Execute a verificação de espaço em disco no ponto de montagem atual:
```bash
df -h .
```
Garantir que a partição possui pelo menos $10\%$ de espaço livre.

### 3. Verificação de Processos Zumbis e Sobrecarga
Identifique os principais consumidores de memória e CPU:
```bash
ps aux --sort=-%mem | head -n 10
```

### 4. Diagnóstico de Portas de Rede em Escuta
Identifique serviços locais ativos:
```bash
ss -tulpn | head -n 20
```

### 5. Resumo e Recomendações
Produza um relatório executivo com:
- **Status Geral:** `HEALTHY` (Saudável), `WARNING` (Alerta de Recursos) ou `CRITICAL` (Sobrecarga).
- **Pontos de Atenção:** Gargalos identificados (ex.: falta de swap, RAM baixa, processos órfãos).
- **Ações Corretivas Sugeridas:** Comandos sugeridos para liberação de memória ou encerramento de processos.
