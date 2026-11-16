# Sprint — v0.5.3 Sprint 1: Liberdade básica

> **Status:** 📋 Aguardando comando de início · **ADRs:** 046 (parte), 048, 049 · **Achados:** G-01, G-02, G-03, G-05, G-06, G-08, G-09 · **CA:** CA-01 a CA-05

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
