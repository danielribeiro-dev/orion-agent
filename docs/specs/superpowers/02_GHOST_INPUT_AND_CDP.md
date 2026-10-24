# Superpoder 02 — Ghost Input, Autoclicker Cognitivo & Context Typer

> Especificação de automação em segundo plano sem roubar o mouse físico do usuário e digitação contextual assistiva.

---

## 1. O Problema da Automação Tradicional de SO

Softwares convencionais de automação (RPA, AutoHotkey, xdotool básico) movem o cursor do usuário na tela física. Se o usuário estiver trabalhando ou navegando, o robô "luta" pelo controle do mouse, tornando a automação impraticável no dia a dia.

---

## 2. A Solução: Injeção Fantasma (Ghost Input)

```
┌────────────────────────────────────────────────────────┐
│                      ORION Core                        │
└───────────────────────────┬────────────────────────────┘
                            │
            ┌───────────────┴───────────────┐
            ▼                               ▼
[Automação Web em Background]     [Automação de Sistema (OS)]
  Chrome DevTools Protocol (CDP)   Linux Kernel /dev/uinput Virtual HID
  • Cliques e digitação sem foco    • Teclado e mouse virtuais paralelos
  • Abas rodam em headless/ocultas  • Não interfere no mouse real do usuário
```

### 2.1 Context Typer ("Write-Where-Pointed")
- O usuário está no terminal ou editor e diz por voz:
  > *"Orion, digita o comando para subir o postgres via docker-compose."*
- O ORION consulta o foco atual via XDG Desktop Portal/Acessibilidade e simula a digitação no local exato do cursor, emitindo um sinal sonoro de confirmação para o usuário apenas bater `Enter`.

### 2.2 Autoclicker Cognitivo com Detecção de Padrões
- Se o usuário repete a mesma ação de interface 3 vezes em um intervalo curto (ex: copiar dados de uma planilha e colar em um sistema web), o ORION identifica o padrão via `pattern_observer` e sugere:
  > *"Notei que você está repetindo esse preenchimento. Deseja que eu execute os 20 itens restantes em background?"*
