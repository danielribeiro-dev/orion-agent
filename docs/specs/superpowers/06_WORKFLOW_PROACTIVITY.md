# Superpoder 06 — Proatividade de Workflow & Sensores de Vida (Context Engine)

> Especificação de antecipação contextual: Git Guard, Modo Foco, Protocolo Babá e Briefing Matinal executivo.

---

## 1. Monitoramento Passivo sem Consumo de CPU (Linux DBus Hooks)

Em vez de rodar scripts pesados em loop infinito (`while True`) verificando o estado do computador, o ORION conecta-se diretamente aos sinais de barramento do sistema operacional (**Linux DBus**):

- `org.freedesktop.ScreenSaver` ── Detecta quando a tela foi bloqueada ou desbloqueada.
- `org.freedesktop.NetworkManager` ── Detecta troca de rede Wi-Fi (SSID).
- `org.freedesktop.UPower` ── Detecta nível de bateria e se o carregador foi plugado/desplugado.

O consumo de recursos desse monitoramento é **virtualmente zero** (orientado a interrupções de hardware).

---

## 2. As Habilidades Proativas em Detalhe

### 2.1 Git Guard (Guardião de Código)
- Quando o usuário bloqueia a tela e se afasta do computador, o ORION verifica se há repositórios de trabalho com alterações não salvas ou sem commit no workspace ativo.
- Se houver trabalho em risco, emite notificação ou resumo sonoro: *"Danvic, você deixou 3 arquivos modificados sem commit no branch feature-x."*

### 2.2 Modo Foco Contextual
- Ao detectar a abertura de aplicações de foco (IDEs pesadas, jogos ou chamadas de vídeo), o ORION silencia notificações e suspende tarefas pesadas de indexação em background.

### 2.3 Protocolo Babá (Proteção Ativa)
- Comando verbal ou atalho de segurança: *"Orion, ative o Protocolo Babá"*.
- O ORION encerra programas de trabalho confidenciais, bloqueia comandos perigosos e exige a *Voice Passphrase* para liberar o sistema novamente.

### 2.4 Morning Summary Executivo
- Na primeira interação da manhã (ao ligar o computador ou emitir a saudação inicial), o ORION apresenta um briefing de 4 linhas:
  1. Estado da máquina e bateria.
  2. Onde parou o trabalho na noite anterior (lido da Main Timeline).
  3. Lembretes e metas registradas.
  4. Pergunta proativa: *"Deseja que eu reabra os arquivos do projeto X?"*
