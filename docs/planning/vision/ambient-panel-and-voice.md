# Visão — Aba Ambiente e Voz sobre o Daemon

> **Status:** Documentado na Sprint 7 (v0.5.0), implementação em v0.6.0 (voz) e v0.7.0 (desktop). Ver ADR-032 e ADR-034.

## Problema
Com o daemon ativo e sem terminal nem áudio, o ORION precisa de um jeito de falar com o Senhor. A Sprint 7 resolve o mínimo (notificação nativa com botões e Inbox). Esta visão descreve o restante.

## Aba flutuante (peek)
- Pequena aba na borda da tela que se estende ao passar o mouse e se recolhe depois; arrastável e ocultável.
- Mostra mensagens do ORION, botões de ação (Aprovar, Negar, Abrir) e, **opcionalmente**, os pensamentos (`ui.show_thinking`, desligado por padrão).
- A aba inteira é opcional (`ui.panel`).
- É apenas um cliente do IPC do daemon; não contém lógica de agente.

## Restrições de plataforma (verificadas em 09/11/2026)
- GNOME no Wayland (ambiente do Senhor) não oferece layer-shell nem "sempre no topo" por aplicação. Há bandeja (`StatusNotifierWatcher`) e notificações com ações.
- Sway, Hyprland e KDE oferecem layer-shell, onde a aba encostada na borda é viável.
- Caminho: shell Tauri (v0.7.0) com janela sem borda; no GNOME, fallback para bandeja + janela normal, ou extensão do GNOME Shell como alternativa a avaliar.

## Voz (v0.6.0)
- Wake word, STT e TTS (ver `docs/architecture/AMBIENT_VOICE.md`) são mais um cliente do IPC.
- Ordem de saída do roteador: cliente anexado, notificação nativa, Telegram, voz. Voz respeita modo silencioso, bateria e orçamento.
- Escuta contínua é opt-in separado do autostart do daemon.

## Requisitos herdados da Sprint 7
Stream de eventos estável, canal de pensamentos separado, notificações com ação, Inbox de pendências e aprovação por cliente.
