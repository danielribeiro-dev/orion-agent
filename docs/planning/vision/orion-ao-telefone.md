# Visão: ORION ao telefone (proposta 36)

> **Status:** PROPOSTA, aguardando decisão do Senhor. Sem ADR, sem spec congelada, nada em `src/` muda (Doc-First).
> **Data:** 17/11/2026. Continuação de [`superpoderes-propostas.md`](superpoderes-propostas.md) e [`superpoderes-propostas-2.md`](superpoderes-propostas-2.md). Aplicam-se as mesmas regras gerais (PEP em toda ação mutante, step-up nuclear, Brain/Body, dados só em `~/.orion/`, idle = 0 token).
> **Relaciona-se com:** item 1 (voz), item 10 (multi-dispositivo), ideia 34 (ações físicas), `docs/architecture/AMBIENT_VOICE.md`, specs `docs/specs/superpowers/01` (câmera sob demanda) e `03` (cofre e passphrase de voz), ADR-032 (Telegram).

## Cenário-alvo

O Senhor está na rua ou na escola. Precisa imprimir algo, mas a impressora do escritório está sem papel e só o pai está lá, sem olhar o celular. O Senhor fala com o ORION pelo Telegram e pede que ele avise o pai. O ORION confere se há alguém no escritório, fala no ambiente com a voz local que o Senhor já usa em casa ("Daniel pede que você coloque papel na impressora") e responde ao Senhor quando o recado for entregue. No escritório não sobra áudio nenhum além da fala do ORION; a conversa do Senhor com o ORION corre só pelo Telegram.

## Estado atual (verificado no código)

- O canal Telegram do daemon usa a **Bot API** (`src/orion/notify/telegram.py`, ADR-032): envia mensagens, recebe resposta de botões e só aceita o dono (`chat_id`). Aprovação nuclear remota já é proibida e recusada no roteador.
- Voz (wake word, STT, TTS) está só na documentação (`AMBIENT_VOICE.md`), planejada para a v0.6.0.
- Não há câmera, nem fala no ambiente, nem ligação.

## Restrições da plataforma (pesquisa de 17/11/2026, sujeita a revalidação)

1. **Bots da Bot API não fazem nem recebem chamadas de voz.** Há pedido aberto no rastreador do Telegram para isso; hoje bots só trocam mensagens, inclusive mensagens de voz.
2. **Ligação real só por conta de usuário (userbot)**, com bibliotecas como `tgcalls`/`pytgcalls` ou MadelineProto. A documentação do `tgcalls` descreve chamadas privadas como "funcionando em desenvolvimento, mas fora da versão de release". Não foi confirmado que a versão atual atende chamadas 1 a 1 e transmite áudio. Exige prova de conceito antes de qualquer promessa.
3. **Risco de conta:** automatizar conta de usuário pode violar os termos do Telegram e causar banimento; seria necessário um número dedicado ao ORION.
4. Formato de áudio de chamada citado pela biblioteca: PCM 16 bits, 48 kHz.

## Os três caminhos

| Caminho | Experiência | Maturidade | Risco |
| :--- | :--- | :--- | :--- |
| **A. Mensagens de voz no Telegram (Bot API)** | Walkie-talkie: o Senhor grava um áudio, o ORION transcreve, age e responde com áudio na mesma voz. | Suportado hoje pela API oficial. | Baixo |
| **B. Ligação real via userbot** | O Senhor liga e o ORION atende em tempo real. | Frágil e pouco documentado. | Banimento, instabilidade |
| **C. Ligação por WebRTC próprio** (PWA ou app via rede privada) | Ligação em tempo real e full-duplex, fora do Telegram. | Tecnologia madura; o cliente é construído por nós. | Baixo, controle total |

**Recomendação:** A primeiro, depois C. B só se uma prova de conceito mostrar estabilidade e o Senhor aceitar o risco de conta.

## Fases propostas

### Fase 1: voz por mensagem de áudio (alvo v0.6.0, caminho A)
- Receber `voice` no canal Telegram do daemon, apenas do `chat_id` do dono.
- Transcrição local (Faster-Whisper), resposta do agente, síntese local (Piper) enviada de volta como mensagem de voz.
- Mesmo pipeline de saída do roteador (cliente anexado, notificação, Telegram, voz), respeitando modo silencioso e `BudgetGuard`.
- **Critério de aceite:** "De fora de casa, mando um áudio pedindo o status do último job; recebo em até alguns segundos uma resposta falada, com a mesma voz que o ORION usa em casa e sem nenhum áudio saindo na minha casa."
- **Limites:** nenhuma ação nuclear por voz; áudio e transcrição ficam em `~/.orion/`; nada de áudio vai a provedor externo sem consentimento.

### Fase 2: falar no ambiente e presença (caminho A + câmera)
- Nova tool `speak_in_room` (falar no alto-falante local) com **PEP próprio de ação física** (ver abaixo).
- Verificação de presença sob demanda: captura em rajada curta, detecção de que há uma pessoa na cena, sem reconhecimento facial, sem gravar nada (spec 01).
- Fluxo: pedido do Senhor, checagem de presença, aviso sonoro curto, fala do recado, confirmação de volta ao Senhor ("recado entregue" ou "não encontrei ninguém no escritório").
- Bônus: estado da impressora por IPP (`media-empty` em `printer-state-reasons`) para o ORION avisar antes de o Senhor pedir.
- **Critério de aceite:** "Peço pelo Telegram para avisar meu pai; o ORION confirma que há alguém no escritório, fala o recado com a minha voz de ORION e me confirma depois."
- **Limites:** só em dispositivos e cômodos habilitados por configuração; horário silencioso; limite de falas por hora; texto sempre em nome do ORION e do Senhor, nunca imitando a voz de uma pessoa.

### Fase 3: ligação em tempo real (caminho C, e B apenas se validado)
- Cliente WebRTC (PWA) servido pelo daemon, acessível por rede privada autenticada; áudio full-duplex com detecção de fala e interrupção.
- Mesmo núcleo de voz da Fase 1; só muda o transporte.
- **Critério de aceite:** "Toco em Ligar no celular e converso com o ORION sem atraso perceptível; ele executa pedidos com as mesmas regras do PEP."
- **Provas de conceito antes de decidir B:** estabilidade de 1 hora de chamada, eco e latência, comportamento do Telegram com o número dedicado.

## Classe de PEP para ações físicas (proposta)

Hoje o PEP tem níveis 0 a 3 para ações no sistema. Ações que afetam o ambiente físico (falar em voz alta, acender luz, ligar equipamento) precisam de uma **classe própria**, a decidir em ADR:

- `speak_in_room`, `camera_presence_check`: nível 2 por padrão (aprovação do Senhor na primeira vez por cômodo; depois regra explícita e revogável).
- Ações com risco físico (equipamentos, hardware): nível 3 ou superior, nunca autorizadas só por voz ou áudio remoto.
- Nenhuma regra, hook, subagente ou agendamento pode elevar essas ações acima do que o Senhor configurou. Ação nuclear segue exigindo step-up do SO e é recusada em canal remoto (já é o comportamento do Telegram hoje).

## Segurança e privacidade

- **Quem fala é o dono?** Origem apenas do `chat_id` do Senhor; opcionalmente passphrase falada com verificação local de voz (spec 03) para ações acima do nível 1. Perder o celular não deve dar controle do ORION: bloqueio remoto (`/lock`) e confirmação no desktop para ações físicas.
- **Instruções por voz são entrada não confiável.** Transcrições passam pela mesma defesa contra injeção de prompt do restante; o conteúdo de um áudio nunca muda o nível de PEP.
- **Terceiros.** A câmera captura quem está no cômodo. Exige aviso visível (por exemplo, LED ou sinal sonoro), conversa prévia com quem convive no local, nenhuma gravação e nenhum reconhecimento facial. Verificar com o Senhor se, em seu contexto, isso exige consentimento formal.
- **Escuta contínua** continua opt-in separada do autostart do daemon.
- **Disponibilidade.** O computador de casa precisa estar ligado com o daemon ativo; um nó dedicado (mini-PC ou Raspberry Pi) é opção para "sempre disponível". Se o ORION estiver offline, o Telegram responde com mensagem de estado, nunca fica mudo.

## Custos e desempenho

- Latência estimada de 2 a 4 segundos por turno com STT e TTS locais; a ser medida (resultado depende do hardware).
- Idle continua em zero token: o daemon apenas mantém a conexão com o Telegram.
- Cada resposta consome tokens normalmente; teto do `BudgetGuard` vale também para chamadas e áudios.

## Riscos

| Risco | Mitigação |
| :--- | :--- |
| Promessa de "ligação" que a plataforma não sustenta | Começar pelo caminho A e vender como "voz pelo Telegram"; B só após prova de conceito. |
| Banimento de conta no caminho B | Número dedicado, uso opt-in e aviso claro; preferir o caminho C. |
| Câmera em ambiente compartilhado | Presença sem identificação, sem gravação, com aviso e configuração por cômodo. |
| Comando remoto indevido | Lista de contas, PEP por classe, passphrase de voz, `/lock`. |
| Ruído e falsos positivos de voz | Push-to-talk no caminho A; limites de frequência e confirmação ao Senhor. |

## Próximos passos (se o Senhor aprovar)

1. Decidir por ADR: caminho A como primeiro alvo e a classe de PEP para ações físicas.
2. Incluir a Fase 1 no escopo da v0.6.0 (voz sobre o daemon) e as demais fases no roadmap posterior.
3. Fazer a prova de conceito do caminho B/C em protótipo descartável fora de `src/` antes de qualquer promessa pública.
4. Só então escrever `VERSION.md` e `sprints/sprint-N.md`.
