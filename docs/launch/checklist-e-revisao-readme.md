# Lançamento do ORION: checklist e revisão do README

> Rascunho de trabalho (16/11/2026). Não commitado. Baseado no README e no ROADMAP atuais.
> Regra: nada aqui altera `src/`. Mudanças no repositório (CI, SECURITY.md, README) pedem confirmação do Senhor.

## 1. Revisão do README (o que eu mudaria)

### Bloqueadores (corrigir antes de qualquer post com link)

| # | Onde | Problema | Correção |
|---|---|---|---|
| R1 | `README.md:22` | Badge diz `v0.5.2-alpha`, mas `pyproject.toml` e `src/orion/__init__.py` dizem `0.5.0-alpha` nesta branch. Se `orion --version` divergir do badge, a primeira pessoa que testar nota. | Conferir na `main` e alinhar versão do pacote, badge e tag. |
| R2 | `README.md:35-66` | A demo é texto traduzido. Quem chega pelo link não vê o produto em movimento. | Gravar GIF/vídeo de 30 a 60 s (ver seção 3) e colocar acima da dobra. |
| R3 | `README.md:93-99` | Instalar exige `git clone` + `scripts/install.sh`. É o maior ponto de atrito. | Oferecer `uv tool install` / `pipx install` ou um instalador de uma linha. Verificar se o nome `orion-agent` está livre no PyPI. |
| R4 | `README.md:21` | Plataforma só Linux, macOS "untested". É honesto, mas limita quem testa. | Manter honesto agora; atualizar o badge só quando Mac/Windows forem testados de verdade. |
| R5 | `docs/planning/ROADMAP.md` §1 | A matriz "Superando o Mercado" afirma coisas sobre Claude Code, Antigravity, OpenHands, Aider. Se estiver desatualizada, vira munição contra o projeto. | Revisar cada célula contra a versão atual de cada ferramenta, ou tirar a matriz da vitrine pública. Não publicar comparação não verificada. |

### Melhorias de impacto

- **Primeira tela.** Hoje a seção "Why" abre com termos internos ("Event-sourced cognition", "PEP"). Abra com resultados que a pessoa sente:
  1. Pergunta antes de apagar ou executar algo perigoso.
  2. Lembra entre sessões, sem repetir contexto.
  3. Gasta zero token quando está parado.
  4. Mostra quanto custou cada turno, em USD e BRL.
  Os termos técnicos descem para a seção de arquitetura.
- **Tagline.** Escolha uma e use sempre (README, bio, posts): por exemplo "The personal engineering agent that asks before it acts, remembers, and costs you nothing when idle."
- **Números de qualidade.** "2123 testes, 93,6% de cobertura" são badges estáticos e vão desatualizar. Um workflow de GitHub Actions rodando a suíte (sem chamadas pagas, como a regra do projeto já exige) dá badge real. Hoje não há `.github/`.
- **Comparação honesta.** Uma tabela curta "ORION vs Claude Code vs agentes locais" com só o que dá para provar: soberania, auditoria, custo ocioso, offline. Diga o que o ORION ainda não faz (voz, Mac/Windows).
- **Narrativa de origem.** O próprio repositório registra que o ORION foi desenvolvido com Claude Code e depois passou a rodar sobre si mesmo (dogfooding). Isso é uma história forte e honesta ("um agente construído por um agente, auditado por testes"). Quem postar sem contar vai ser perguntado no Hacker News. Decisão do Senhor: contar de frente.
  Sugestão de texto fiel aos fatos (ajustar ao que de fato aconteceu): "Comecei uma primeira versão em outro repositório no ano passado, enquanto aprendia a programar, e a arquitetura ficou bagunçada. Recomecei do zero com o que aprendi: eu defino a arquitetura, as especificações e as decisões (ADRs); o Claude Code implementa sob essa direção, e a suíte de testes audita o resultado." Evite "construí sozinho do zero": é a frase que o histórico do repositório desmente.
- **Arquivos internos.** `ORION.md` (briefing para o Claude dentro do ORION) e `.claudex/` aparecem para quem navega. Podem confundir ou impressionar. Se ficarem, linkar uma frase no README explicando "build in public".
- **Emojis no README.** A TUI proíbe emojis, mas o README usa. Não é erro (GitHub), só uma incoerência que alguém vai comentar. Opcional: reduzir.

### Higiene do repositório (falta tudo isto)

- [ ] `SECURITY.md` (essencial para um agente que mexe no sistema): como reportar vulnerabilidade.
- [ ] `CONTRIBUTING.md` curto, apontando o fluxo Doc-First e `good first issue`.
- [ ] Templates de issue (bug com `orion --version` e `/doctor`, ideia de feature).
- [ ] GitHub Topics: `ai-agent`, `terminal`, `tui`, `mcp`, `local-first`, `jarvis`, `llm`, `python`.
- [ ] Imagem de preview social (1280x640) com o banner ASCII.
- [ ] Ativar GitHub Discussions.
- [ ] Rodar varredura de segredos no histórico antes de tornar público (há `run_secret_scanning` disponível aqui) e confirmar que o repositório está público.
- [ ] Release com tag e notas de versão (`orion update` já depende de tags).

## 2. Checklist de lançamento

### Fase A: agora (build in public leve, sem anúncio)
- [ ] Resolver R1 a R3 acima.
- [ ] Gravar 3 clipes curtos (ver seção 3).
- [ ] Criar perfil/handle consistente no X e usar o mesmo nome no GitHub.
- [ ] Postar 1 clipe por semana no X e no LinkedIn com uma história técnica curta.
- [ ] Participar de r/LocalLLaMA, r/commandline e r/selfhosted por 2 a 3 semanas antes de postar o seu.
- [ ] Anotar quem comenta e testa: são seus primeiros contribuidores.

### Fase B: lançamento (Linux + Mac, instalação em um comando)
- [ ] Instalação testada em Ubuntu, Fedora, macOS (Intel e Apple Silicon) em máquinas limpas.
- [ ] `/doctor` sem falhas em instalação nova.
- [ ] Modo sem chave: funciona com Ollama ou com modelo gratuito, para quem quer testar sem pagar.
- [ ] Vídeo de 2 a 3 min no YouTube e o GIF no README.
- [ ] Terça a quinta, manhã no horário dos EUA (Leste), Show HN. Fique online 4 a 6 horas respondendo.
- [ ] Mesmo dia ou dia seguinte: Reddit (um subreddit por vez, com post técnico, não anúncio), X thread, LinkedIn.
- [ ] Ter 5 issues "good first issue" abertas antes do post.

### Fase C: voz, Windows e cockpit
- [ ] Clipes de voz ("Senhor, posso executar...") para Reels, Shorts e TikTok.
- [ ] Demo "desliguei o wifi e ele continua" (offline).
- [ ] Segundo ciclo de lançamento (Product Hunt, YouTubers de terminal e IA).

## 3. Clipes para gravar (custo zero)

O harness `tests/lab/` já tem provider roteirizado, e `tests/lab/launcher.py --fullscreen` abre a tela cheia sem chamar modelo pago. Isso permite gravar demos determinísticas e repetíveis.

1. **"Ele pergunta antes de agir"** (30 s): pedido, edição, painel `[PEP]` pedindo aprovação, teste passando.
2. **"Zero tokens quando parado"** (30 s): `orion daemon status`, agendamento disparando, notificação, custo mostrando US$ 0.
3. **"Lembra de você"** (45 s): sessão nova, `/recall`, ele retoma uma decisão antiga.

Ferramentas: `vhs` (Charm) para gravação roteirizada em GIF, ou `asciinema` + `agg`. Já existem `tui-mcp` e `ptywright` instalados para capturas.

## 4. Pontos de atenção

- **Reddit:** regras de autopromoção por subreddit. Leia cada uma. Poste uma história ("como medi o gasto de tokens e cortei X%") com o link no fim.
- **Hacker News:** título sóbrio, sem superlativos, sem "supera". Primeiro comentário seu explicando motivação, limites e o que falta.
- **Segurança como discurso:** um agente que mexe na máquina será questionado. Tenha pronta a resposta sobre o PEP, o step-up do SO e a auditoria, com link para `tests/e2e/test_security_audit.py`.
- **Claims:** diga "posição": soberano, auditável, frugal. Evite "melhor que". Prove com demo e número.
