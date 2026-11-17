# Sprint — v0.5.3 Sprint 1: Liberdade básica

> **Status:** ✅ Implementada em 16/11/2026 · **ADRs:** 046 (parte), 048, 049 · **Achados:** G-01, G-02, G-03, G-05, G-06, G-08, G-09 · **CA:** CA-01 a CA-05

## Objetivo
Consertar o que hoje é defeito, sem ainda trocar o modelo de decisão: senha verificada de verdade, `sudo` que funciona, escopo do usuário, ledger ligado e web aberta.

## Escopo
1. **Askpass** (`governance/askpass.py`, `runtime/tools/run_command.py`):
   - `run_command` reescreve `sudo` para `sudo -A` e exporta `SUDO_ASKPASS` apontando para `orion-askpass` (entry point do pacote).
   - O helper fala com a sessão por um socket efêmero 0600 (`$XDG_RUNTIME_DIR/orion/askpass-<pid>.sock`) carregando só o pedido; a TUI mostra um overlay mascarado (tela cheia) ou popup zenity/kdialog (sem TUI). A senha volta ao helper e sai pelo stdout para o sudo. Nunca passa pelo engine, pelo transcript, pela auditoria nem pelos logs.
   - Quem verifica é o próprio sudo; o timestamp do sudo evita repetir (documentar `timestamp_type` no `/doctor`).
2. **Chaveiro opt-in** (`orion setup sudo`):
   - Guarda a senha no Secret Service (`secretstorage`, coleção padrão, atributo `orion=sudo`).
   - O helper só preenche sozinho quando o PEP marcou o pedido como `sudo_safe` (nesta sprint: regras determinísticas; na Sprint 2, o classificador). Para qualquer comando da faixa Nuclear, o helper recusa preencher e pede presença.
   - `orion setup sudo --forget` apaga; `--sudoers` gera `/etc/sudoers.d/orion` com NOPASSWD para uma lista que o Senhor edita antes, validada com `visudo -c`, aplicada com `pkexec`.
3. **Nuclear verificado** (`governance/nuclear.py`):
   - Ordem: polkit (`pkexec /bin/true` com ação própria `org.orion.nuclear`) quando há agente polkit; PAM do usuário (`python-pam`, serviço `orion` ou `login`) com overlay mascarado na tela cheia; fprintd quando `pam_fprintd` estiver no serviço.
   - Remover "qualquer texto não vazio vale" nos três caminhos; senha errada nega e audita `nuclear_stepup:failed`.
   - Nunca ler `/dev/tty` cru com a tela cheia ativa (G-03).
4. **Escopo do usuário** (`pep.py`, `permissions.py`):
   - `WorkspaceScope` passa a `[$HOME, montagens do usuário em /media/$USER e /run/media/$USER]`. Escrita em qualquer repositório dentro do escopo não escala.
   - Caminhos sensíveis continuam escalando: `~/.ssh`, `~/.gnupg`, `~/.config/systemd`, `~/.bashrc/.zshrc/.profile`, governança do `~/.orion`. Fora do escopo (`/etc`, `/usr`, `/var`): escala (Sprint 2 classifica).
   - A opção "sempre" volta para escritas fora do escopo que não sejam sensíveis.
5. **Ledger ligado**: instanciar `CommandTrustLedger` na sessão e no daemon; gravar sucesso de comando aprovado; assinatura por prefixo normalizado (`git push origin *` ≠ `git push --force*`); teste de persistência entre sessões.
6. **Web aberta** (`runtime/web_policy.py`, `runtime/search/`):
   - Allowlist vira blocklist (`~/.orion/web_blocklist.json`, editável por `/web block|unblock|list`). O antigo `web_allowlist.json` é lido uma vez e ignorado depois (mensagem no `/doctor`).
   - Mantidos: bloqueio de IP privado em cada redirecionamento, tipos de conteúdo de texto, limites de tamanho, filtro de injeção.
   - User agent de navegador comum para fetch; `orion-agent/0.5` só em APIs.
   - `SearchProvider` com cadeia: Brave (`BRAVE_API_KEY` no `.env`), `ddgs` (biblioteca), SearXNG (`settings.web.searxng_url`). Primeiro que responder vence; 429/anti-bot passa ao próximo; resultado informa o provedor.
7. **`CLAUDE.md`**: aplicar a linha "Segurança" de `VERSION.md` §2.4.

## Fora do escopo
Faixas, classificador e reversibilidade (Sprint 2). O modo padrão continua `accept-edits` até a Sprint 2.

## Testes
- `tests/unit/test_askpass.py`: socket, recusa para Nuclear, chaveiro falso, senha fora de logs/auditoria (varredura).
- `tests/unit/test_nuclear_auth.py`: PAM falso (aceita/nega), polkit simulado, overlay sem `/dev/tty`.
- `tests/unit/test_search_provider.py`: cadeia com provedores falsos, sem rede.
- `tests/e2e/test_security_audit.py`: escopo do usuário, sensíveis escalam, IP privado negado, segredos não lidos.
- Validação manual do Senhor: `sudo apt update` pelo ORION no GNOME; diálogo polkit; senha errada.

## Critérios de saída
CA-01 a CA-05 verdes; `ruff`, `mypy`, cobertura >= 85%; commit `feat(governance): v0.5.3 Sprint 1 — liberdade básica`.

## Registro de execução (16/11/2026)
Entregue conforme o escopo, com validação real numa sessão de tela cheia (`tui-mcp`, provider roteirizado, `HOME` isolado, sem display) contra o **sudo-rs 0.2.13** desta máquina (Ubuntu 26.04).

- **Askpass** (`governance/askpass.py`, `orion/askpass.py`): broker por comando com socket 0600 em `$XDG_RUNTIME_DIR/orion` (0700), token de uso único, **SO_PEERCRED**: só responde a um processo do mesmo usuário cujo pai é o `sudo` (comm `sudo`; `/proc/<pid>/exe` do sudo setuid não é legível). Um script dentro do comando que roube o token é recusado. O helper é um script gerado em tempo de execução (`exec <python> -m orion.askpass`), então funciona em venv, `install.sh` e checkout. Até 3 pedidos (sudo-rs chama o askpass 3 vezes); cancelar faz o sudo abortar sem tentar autenticar.
- **Chaveiro**: `orion setup sudo` só guarda depois de `sudo -k -S -v` aceitar; marca `~/.orion/sudo_keyring` liga o preenchimento (sem marca, nem toca o D-Bus). Preenche só a 1ª tentativa e só o que `is_sudo_safe` aprova (instalar, atualizar, consultar, reiniciar serviços; nunca composto, troca de usuário, shell, leitura de segredo ou Nuclear). Senha antiga no chaveiro cai para a pergunta ao Senhor com aviso. `--sudoers [--apply]` gera e instala lista revisada (recusa `ALL` e shells).
- **Nuclear**: polkit (`pkexec --disable-internal-agent /bin/true`) com display; sem agente, PAM do usuário (`python-pam`, serviço `orion` se existir, senão `login`) pela senha mascarada da interface. Removidos "qualquer texto vale" e a leitura de `/dev/tty`. Auditoria `nuclear_stepup:failed:<método>`.
- **Escopo do usuário**: `WorkspaceScope.user_space` (`$HOME`, `/media/$USER`, `/run/media/$USER`, `/mnt/$USER`, e o workspace se estiver fora do HOME). Sensíveis (`~/.ssh`, `~/.gnupg`, rc do shell, autostart/systemd do usuário, credenciais de nuvem/git/docker) escalam sempre e nunca viram "sempre". Fora do escopo, "sempre" grava regra allow para a pasta.
- **Ledger ligado** na sessão (e no daemon, que usa a mesma `AgentSession`), aprendendo só o que o Senhor aprovou e terminou com exit 0.
- **Web aberta** (blocklist `~/.orion/web_blocklist.json`, `/web block|unblock|list`, lida a cada uso) e **`SearchProvider`** em cadeia Brave → ddgs → SearXNG → DuckDuckGo HTML, com o provedor informado no resultado. `settings.web.{searxng_url, search_order}`.
- **Interface**: senha mascarada no input da tela cheia (nunca vai ao histórico nem à transcrição), prompt sem eco no modo clássico, zenity sem terminal. `/doctor` mostra askpass, chaveiro, presença nuclear, web e busca.

### Desvios e decisões tomadas na execução
1. **Ledger endurecido além da spec** (furos achados ao ligar): comandos compostos (`;`, `&&`, `|`, redirecionamento, `$(...)` mesmo entre aspas) nunca são aprendidos nem consultados, porque herdariam a confiança do primeiro; a assinatura do git inclui todas as flags (`git push` ≠ `git push --force` ≠ `git push +main`); interpretadores (`python`, `bash`, `npx`, `make`...) só casam o literal exato; `rm`, `mv`, `chmod`, `curl`, `sudo`, git destrutivo nunca entram.
2. **Presença verificada substitui o "y/n"**: com polkit/PAM aceito e sem outra escalada, o PEP não abre o modal de novo (eram duas perguntas para o mesmo ato).
3. **Ação polkit própria (`org.orion.nuclear`) não instalada**: exigiria root para gravar em `/usr/share/polkit-1/actions`; usa-se a ação padrão do `pkexec` com aviso na TUI mostrando o comando. Fica como melhoria opcional.
4. **`sudo` em shell de segundo plano** não usa o askpass (o broker vive só durante o comando em primeiro plano).
5. Dependências novas: `secretstorage`, `python-pam`, `ddgs`.

### Validação
- Suíte: 2283 testes, cobertura 94%, `ruff` e `mypy` limpos; lab de TUI completo.
- Novos: `test_askpass.py` (inclui ponta a ponta com `sudo` falso no PATH e checagem real de peer), `test_nuclear_auth.py`, `test_search_provider.py`, `test_user_scope_and_ledger.py`, `test_sprint1_freedom_ui.py`; e2e `test_security_audit.py` com 6 cenários v0.5.3.
- Rodada real: `sudo -k apt update` → modal → senha mascarada → Esc → "Authentication required but not attempted"; escrita em outro repositório sem pergunta; `rm -rf` → senha mascarada (PAM) → Esc → negado; `/web block`; `/doctor`. A senha digitada não aparece em nenhum arquivo do `~/.orion`.
- **Pendente do Senhor (CA-01/CA-07 manuais):** `sudo apt update` com a senha verdadeira; diálogo polkit no GNOME (com display); senha errada no polkit; `orion setup sudo` com o chaveiro real.
