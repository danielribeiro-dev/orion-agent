# ORION-Agent — Modo Ambiente & Presença de Voz Headless

> Especificação da experiência de voz e presença estilo J.A.R.V.I.S.: o computador pronto para conversar sem necessidade de janelas abertas.

---

## 1. Operação Headless (Em Segundo Plano)

O ORION roda como um daemon de usuário no Linux (`systemd --user`).

- Ao iniciar o sistema operacional, o serviço sobe silenciosamente.
- Se a flag de escuta contínua estiver ativada, o microfone monitora a palavra de ativação (**Wake Word**) sem travar a CPU e sem abrir terminal.
- O usuário pode estar trabalhando em qualquer programa, lendo um documento ou afastado da mesa, e simplesmente falar:
  > *"Orion, compile o projeto e rode os testes em segundo plano."*
- O ORION processa a intenção, executa as ações e responde verbalmente pelo alto-falante:
  > *"Iniciei a compilação. Houve 1 falha no teste de autenticação. Devo abrir o terminal para você verificar?"*

---

## 2. O Pipeline de Áudio

```
[Microfone]
    │
    ▼
[Wake Word Detector (openWakeWord)] ── (99% do tempo: local, ultraleve)
    │ Detectado ("Hey Orion" / "Orion")
    ▼
[Speech-to-Text (STT: Faster-Whisper local)]
    │ Transcreve áudio → Texto
    ▼
[Core ReAct Engine & Linha do Tempo]
    │ Gera resposta e executa ferramentas
    ▼
[Tone-Mirroring Adapter]
    │ Ajusta concisão da fala
    ▼
[Text-to-Speech (TTS: Piper local / Fallback Nuvem)]
    │ Sintetiza áudio
    ▼
[Alto-Falante / Fone]
```

---

## 3. Comportamento Adaptativo e Tone-Mirroring

O ORION não fala a mesma quantidade de texto em todas as situações:

1. **Modo Direto / Executivo (Comandos Rápidos):**
   - Ativado quando o usuário fala frases curtas (ex: *"Orion, feche a branch"*, *"Status da bateria"*).
   - O TTS sintetiza no máximo 1 ou 2 frases curtas, indo direto ao ponto, com zero cortesias prolixas.
2. **Modo Didático / Exploratório:**
   - Ativado quando o usuário faz perguntas de investigação (ex: *"Orion, me explique como funciona a memória tríplice"*).
   - O ORION oferece respostas explicativas e pode, opcionalmente, abrir diagramas ou páginas no navegador se autorizado.
3. **Restrição Orçamentária e de Bateria:**
   - Em caso de quota baixa de API ou bateria fraca no laptop, o assistente prioriza respostas curtas em modo offline gracioso.
