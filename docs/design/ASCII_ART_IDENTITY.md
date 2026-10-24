# ORION-Agent — Identidade Visual e Arte ASCII de Inicialização

> Este documento define a identidade visual do **ORION**, as propostas de arte ASCII para a tela de inicialização (Splash Banner) e a paleta de cores para o terminal (TUI).

---

## 1. O Conceito Visual

A identidade do ORION é inspirada na constelação de Orion — a figura do "Caçador Cósmico" e o arquétipo do parceiro executivo inteligente:
- **Atributos:** Precisão, elegância minimalista, presença sutil e alta densidade de informação limpa.
- **Vibe:** Cyber-editorial moderno (estilo terminal de engenharia avançada de ficção científica realista, sem poluição de efeitos desnecessários).

---

## 2. Paleta de Cores do Terminal (Rich / ANSI Palette)

| Papel | Nome | Hex / ANSI | Exemplo de Uso |
| :--- | :--- | :--- | :--- |
| **Primária (Aura)** | Cyan Cósmico | `#00d2ff` / `bold cyan` | Logo principal, destaques de status, bordas ativas |
| **Secundária (Estelar)** | Azul Órion Profundo | `#3a7bd5` / `blue` | Indicadores de modo, links, tags de categoria |
| **Acentos (Alerta/Ação)** | Âmbar de Ignição | `#f39c12` / `yellow` | Pedidos de confirmação `[Y/n]`, avisos de cota |
| **Acentos (Sucesso)** | Verde Aurora | `#2ecc71` / `green` | Ações verificadas com sucesso, testes passando |
| **Neutro Primário** | Branco Gelo | `#ecf0f1` / `bright_white` | Texto principal de respostas e comandos |
| **Neutro Suave** | Cinza Titânio | `#7f8c8d` / `dim white` | Metadados, timestamps, caminhos de arquivo |
| **Fundo / Painéis** | Grafite Espacial | `#1e272e` | Painéis flutuantes, caixas de diff e tabelas |

---

## 3. Propostas de Arte ASCII Exclusiva

Abaixo estão três propostas de design para a abertura do terminal interativo:

### Opção A: *Stellar Cyber Block* (Imponente, Moderna, Fonte Sólida)

```text
  ██████╗ ██████╗ ██╗ ██████╗ ███╗   ██╗
 ██╔═══██╗██╔══██╗██║██╔═══██╗████╗  ██║
 ██║   ██║██████╔╝██║██║   ██║██╔██╗ ██║
 ██║   ██║██╔══██╗██║██║   ██║██║╚██╗██║
 ╚██████╔╝██║  ██║██║╚██████╔╝██║ ╚████║
  ╚═════╝ ╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═╝  ╚═══╝
```

---

### Opção B: *Constellation Minimalist* (Fina, Estilizada, Arrojada)

```text
   ____  ____  ________  _   __
  / __ \/ __ \/  _/ __ \/ | / /
 / / / / /_/ // // / / /  |/ / 
/ /_/ / _, _// // /_/ / /|  /  
\____/_/ |_/___/\____/_/ |_/   
```

---

### Opção C: *The Hunter Crest* (Hexagonal / Tecnológica com Constelação Integrada — **Recomendada**)

```text
       /\
      /  \        ___  ____  _ ____  _   _
     / /\ \      / _ \|  _ \(_)  _ \| \ | |
    / /__\ \    | | | | |_) | | | | |  \| |
   / /    \ \   | |_| |  _ <| | |_| | |\  |
  /_/      \_\   \___/|_| \_\_|\____/|_| \_|
   *    *    *   [ PERSONAL OPERATING INTELLIGENCE ]
```

---

## 4. O Layout do Banner de Boot Completo

Quando o usuário abrir o comando `orion` no terminal, o cabeçalho exibirá:

```text
  ____  ____  ________  _   __
 / __ \/ __ \/  _/ __ \/ | / /    ORION-Agent  v0.1.0-alpha
/ / / / /_/ // // / / /  |/ /     Personal Operating Intelligence
\____/_/ |_/___/\____/_/ |_/      https://github.com/danielribeiro-dev/orion-agent
────────────────────────────────────────────────────────────────────────
● Daemon: Ativo (Background)  ● Modo: Supervisionado  ● Linha do Tempo: Contínua
● Provedores: 3 Ativos        ● Memória: 100% Local   ● Voz: Pronta (Headless)
────────────────────────────────────────────────────────────────────────
Dica: Digite / para ver os comandos rápidos disponíveis. Use Ctrl+C para sair.
```

Este layout une autoridade técnica, clareza operacional imediata e estética refinada.
