# ORION-Agent — Identidade Visual e Arte ASCII de Inicialização

> Este documento define a identidade visual do **ORION**, as propostas de arte ASCII para a tela de inicialização (Splash Banner) e a paleta de cores para o terminal (TUI).

---

## 1. O Conceito Visual

A identidade do ORION é inspirada na constelação de Orion — a figura do "Caçador Cósmico" e o arquétipo do parceiro executivo inteligente:
- **Atributos:** Precisão, elegância minimalista, presença sutil e alta densidade de informação limpa.
- **Vibe:** Cyber-editorial moderno (estilo terminal de engenharia avançada de ficção científica realista, sem poluição de efeitos desnecessários).

---

## 2. Paleta Oficial do Terminal ("Deep Cosmos & Glacial Platinum")

> Calibrada para conforto ergonômico em sessões prolongadas de trabalho (12h+ sem fadiga visual), com contraste WCAG AAA superior a 13:1 e fidelidade harmônica com a temática cósmica do O.R.I.O.N.

| Papel | Nome | Hexadecimal | ANSI / Rich Style | Exemplo de Uso |
| :--- | :--- | :--- | :--- | :--- |
| **Fundo do Terminal** | Preto Cosmos Profundo | `#0B0E14` | `on #0B0E14` | Base suave que absorve luz sem cansar a vista |
| **Superfície / Caixas** | Grafite Estelar | `#151B23` | `on #151B23` | Cards, caixas de input, painéis de diff |
| **Bordas / Separadores** | Contorno Discreto | `#262F3D` | `#262F3D` | Bordas arredondadas e divisores sutis |
| **Texto Primário (Agente)**| Branco Glacial Suave | `#E6EDF3` | `#E6EDF3` | Texto principal das respostas e leituras |
| **Texto Secundário / Dim**| Cinza Titânio Fosco | `#8B949E` | `dim #8B949E` | Metadados, timestamps, caminhos de arquivo |
| **Input do Usuário** | Branco Puro Iluminado | `#F0F6FC` | `bold #F0F6FC` | Comandos digitados pelo desenvolvedor |
| **Aura Cósmica (Alma)** | Cyan Cósmico | `#00D2FF` | `bold #00D2FF` | Buraco Negro, logo, badges de destaque |
| **Órbita Secundária** | Azul Órion Profundo | `#3A7BD5` | `#3A7BD5` | Links, categorias e status de modo |
| **Diff Adição (+)** | Verde Aurora Suave | `#3FB950` | `bold #3FB950` | Linhas de código adicionadas em diffs |
| **Diff Remoção (-)** | Vermelho Alerta Suave | `#F85149` | `bold #F85149` | Linhas de código removidas em diffs |
| **Alerta / Governança** | Âmbar de Ignição | `#D29922` | `bold #D29922` | Confirmações PEP, avisos e limites de custo |

---

## 3. Propostas de Arte ASCII Exclusiva

Abaixo estão três propostas de design para a abertura do terminal interativo:

### Opção A (a melhor e atualmente a usada): *Stellar Cyber Block* (Imponente, Moderna, Fonte Sólida)

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
