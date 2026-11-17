# Sprint — v0.5.3 Sprint 2: Classificador e reversibilidade

> **Status:** ✅ Implementada em 16/11/2026 · **ADRs:** 046, 047 · **Achados:** G-04, G-10 · **CA:** CA-06 a CA-08

## Objetivo
Trocar a decisão por tool pela decisão por raio de destruição e reversibilidade, com o modo `auto` como padrão, e tornar desfazível o que hoje não é.

## Escopo
1. **Faixas** (`governance/bands.py`): `LIVRE`, `CLASSIFICADA`, `PRESENÇA`, `NUCLEAR` + `BLOCKLIST`. Mapa inicial:
   - Livre: tools de leitura (exceto segredos), `web_*`, escrita no escopo não sensível, comandos de leitura conhecidos (`ls`, `cat`, `git status/log/diff`, `rg`, `pytest`, `ruff`, `mypy`...).
   - Classificada: comando desconhecido, escrita fora do escopo não sensível, MCP mutante, `sudo` não destrutivo, deleção com snapshot.
   - Presença: push para branch protegida (sem force), envio de dados a host novo com a sessão contaminada, criação de unit/timer do sistema, `docker system prune`, deleção acima do teto de snapshot quando o alvo é recuperável de outra forma.
   - Nuclear: `mkfs`, `dd of=/dev/*`, `parted/fdisk/wipefs`, `apt remove/purge` de pacote essencial, escrita em `/etc`, `~/.ssh`, `~/.gnupg`, governança do `~/.orion`, `git push --force` em branch protegida, DROP/TRUNCATE em banco remoto, envio de segredo para fora, deleção sem snapshot possível, `orion update` (ADR-044).
   - Blocklist (nunca, nem em `full`): `rm -rf /` e variantes, fork bomb, `mkfs`/`dd` na raiz montada, `chmod -R 777 /`, `curl|sh` para root.
   - Tool sem faixa declarada = Nuclear (deny by default preservado).
2. **Classificador** (`governance/classifier.py`, porta `RiskClassifierPort`):
   - Estágio 1: regras determinísticas (faixas acima, `nuclear.py:110-141`, ledger). Decide a maioria sem modelo.
   - Estágio 2: só para o resto. Modelo FAST com prompt fixo, entrada = mensagens do Senhor da sessão + a chamada de tool (nunca saídas de tool nem texto do assistente). Saída JSON `{decision: allow|deny|escalate, band, reason}`.
   - Cache por assinatura no ledger; teto diário `origin=classifier` no `BudgetGuard`; sem modelo disponível = `escalate`.
3. **Reversibilidade** (`governance/reversibility.py`):
   - Antes de `rm`, `mv` sobre existente, `>` sobre existente, `git checkout -- .`, `git reset --hard`, `git clean`: resolver alvos (parser de shell conservador; se não resolver, sobe uma faixa), copiar para `~/.orion/trash/<ts>-<id>/` com manifesto (reflink no btrfs, hardlink quando seguro, cópia no resto). Em repositório: `git stash create` + ref `refs/orion/undo/<id>`.
   - Teto padrão 2 GiB por ação e 10 GiB no total; retenção 7 dias (limpeza por evento, nunca por relógio ocioso).
   - `/undo [id]` e tool `undo_last` (Livre) restauram; a linha do turno mostra `● 30 arquivos no lixo do ORION · /undo`.
4. **Aprovação por intenção** (`governance/grants.py`): quando o plano tem passos de Presença, o modal oferece "aprovar o plano" com escopo (comandos/caminhos listados) e TTL de 15 min. Nunca cobre Nuclear nem Blocklist.
5. **Modos**: `plan`, `ask`, `auto` (padrão novo), `full` (pula o estágio 2; Presença vira Classificada; Nuclear e Blocklist intactos). `accept-edits` e `manual` viram aliases (`auto`, `ask`) com aviso no `/doctor`.
6. **Negações**: negação volta ao modelo com motivo e pedido de alternativa; 3 seguidas ou 20 na sessão devolvem ao Senhor (modal).
7. **Sem humano**: Presença e Nuclear viram pendência na Inbox/notificação (ADR-032) com o comando e o motivo; o job espera ou segue sem o passo. Nunca executa.
8. **Subagents**: herdam blocklist, deny, ledger e grants válidos; Presença escala ao pai.
9. **Auditoria**: `decision_source` ganha `band:<faixa>`, `classifier:<stage>`, `grant:<id>`, `snapshot:<id>`.

## Testes
- `tests/unit/test_bands.py`, `test_classifier.py` (provider roteirizado; prova que saídas de tool não chegam ao classificador), `test_reversibility.py` (snapshot, teto, retenção, `/undo`, repo), `test_grants.py`.
- `tests/e2e/test_security_audit.py` reescrito: blocklist em `full`, Nuclear sem senha nega, filho não sobe, sem humano vira Inbox.
- Lab: overlay de Presença e de aprovação de plano.

## Critérios de saída
CA-06 a CA-08 verdes; commit `feat(governance): v0.5.3 Sprint 2 — classificador e reversibilidade`.

## Registro de execução (16/11/2026)
Entregue conforme o escopo, com o PEP decidindo por faixa em vez de por tool. Validação: suíte padrão, `test_security_audit.py` reescrito, lab completo (25 cenários antigos + 3 novos) num PTY real.

- **Faixas** (`governance/bands.py`, `governance/paths.py`): parser de shell conservador (segmento a segmento; `cd` muda o diretório dos seguintes; quebra de linha separa; `sh -c` e `xargs` classificados pelo conteúdo; glob na raiz conta como sistema; `$(...)`, variáveis e `find -delete` marcam alvo não resolvido). Blocklist aplicada ao texto bruto e de novo aos tokens normalizados (`r''m -rf /` não escapa); dispositivos da raiz lidos de `/proc/self/mounts`. Branch protegida por padrão (`main`, `master`, `trunk`, `production`, `prod`, `release*`); branch atual lida de `.git/HEAD` sem subprocesso; branch que não resolve conta como protegida. Tool sem faixa = Nuclear; tool nativa declarada LEVEL_0/1 = Livre; MCP herda do nível (leitura Livre, mutante Classificada). Teste garante que toda tool de `TOOL_LEVELS` tem faixa.
- **Classificador** (`governance/classifier.py`, porta `RiskClassifierPort`): estágio 1 = reversível no escopo (veredito da faixa), ledger e cache de `allow` por assinatura canônica (tabela `classifier_cache` no `command_trust.db`, 7 dias; `deny` nunca é cacheado; sessão contaminada ignora o cache). Estágio 2 = tier FAST, `max_tokens=200`, origem `classifier` com teto de US$ 0,20/dia (também aplicado quando o Senhor sobrescreve `origin_budget_usd`). Entrada = só as falas cruas do Senhor (`run_turn`, antes de menções e recall) + a chamada; teste prova que uma injeção lida por `read_file` não chega a nenhuma chamada do estágio 2. O modelo só sobe a faixa; `allow` com faixa Presença vira `escalate`.
- **Reversibilidade** (`governance/reversibility.py`): `~/.orion/trash/<ts>-<id>/` (0700) com `manifest.json`; hardlink só na deleção e só com `st_nlink == 1`; reflink (`FICLONE`) ou cópia no resto; symlink guardado como link. Git: `git stash create` + `refs/orion/undo/<id>`; `git clean` guarda o que `git clean -n` com as mesmas flags listaria. Pastas regeneráveis (`node_modules`, `.venv`, caches, `build`, `dist`...) não são copiadas e ficam no manifesto. Tetos 2/10 GiB, retenção 7 dias, limpeza no evento de um novo snapshot (nunca por relógio). Restauração preserva a versão atual como `<nome>.orion-undo-<id>`.
- **PEP**: blocklist e segredos negam em todo modo; Nuclear pede presença verificada em todo modo (`challenge_async(required=True)`: a faixa decide, não mais os padrões antigos do `nuclear.py`); `auto` decide por faixa; edição do Senhor no modal refaz faixa, blocklist e snapshot sobre o comando editado. Snapshot falho nega a ação (sem reversibilidade não roda). Linha do turno `● 30 arquivos no lixo do ORION · /undo <id>` (também no `/run`).
- **Grants** (`governance/grants.py`): `exit_plan_mode` ganhou `presence_commands`/`presence_paths`; o modal lista os passos ("Aprovar o plano"); comando casa por tokens iguais (ou prefixo explícito com ` *`), caminho por pasta resolvida; nunca Nuclear nem blocklist; auditoria `grant:<id>`.
- **Modos**: `plan`, `ask`, `auto` (padrão), `full`; `accept-edits` e `manual` são aliases com aviso no `/doctor`. Shift+Tab: plan → ask → auto → full.
- **Negações**: negação do classificador volta ao modelo com motivo e pedido de alternativa; 3 seguidas ou 20 na sessão abrem o modal do Senhor.
- **Sem humano**: daemon (`fire`) liga `set_deferral`; Presença e Nuclear viram item `alert` na Inbox (`payload.pending_action`, faixa, motivo) e o job segue sem o passo (`FireOutcome` `skipped`). Exceção `ActionDeferred` (subclasse de `ActionDenied`).
- **Subagents**: herdam blocklist, deny/ask, grants válidos e a CONSULTA ao ledger do pai (estágio 1); nunca aprendem no ledger nem perguntam; Presença volta ao pai com o passo exato.
- **Auditoria**: `band:livre`, `band:blocklist`, `band:<faixa>` nas negações, `classifier:<rules|ledger|cache|model|none>`, `grant:<id>`, `+snapshot:<id>`, `deferred_inbox:<id>`.
- **`/undo [list|<id>]`** e tool **`undo_last`** (Livre, LEVEL_2: negada no modo plano). `/undo` sem id desfaz o mais recente entre edição de arquivo e snapshot do lixo. `/doctor` mostra modo, classificador e uso do lixo.

### Desvios e decisões tomadas na execução
1. **Leitura não é Livre quando expõe credencial** (revisão adversarial): `cat ~/.ssh/id_rsa`, `read_file` em chave ou `~/.aws/credentials` viram Classificada (antes de enviar o conteúdo ao provedor). Também deixam de ser leitura: `git -c ...`, `git log --output`, `rg --pre`, `sed` com `e`/`w`/`r`, `sort -o`, `uniq a b`, `fd -x`, `env`/`printenv` sozinhos.
2. **Modo `ask` continua perguntando leitura de rede e comandos de leitura** (como o antigo `manual`); `plan`, `auto` e `full` deixam leitura pura passar, então o modo plano agora pode rodar `ls`, `git log`, `pytest` e ler a web.
3. **Sem motor de snapshot, deleção é Nuclear** ("deleção sem snapshot possível"); a sessão e o daemon sempre ligam o motor. `sudo` com deleção é Nuclear (o snapshot não roda como root).
4. **`full` aprova escrita fora do escopo que não seja do sistema** (Classificada sem estágio 2), como a spec manda; `/etc`, `/usr`, `~/.ssh` seguem Nuclear.
5. **Regra `allow` não libera `sudo`** (invariante da v0.5.0 mantida); o classificador pode. Aprovação do Senhor numa dúvida só do classificador conta como aprovação comum: o ledger aprende e "sempre" grava regra.
6. **Estágio 2 desligável por `ORION_CLASSIFIER_MODEL=0`**: ligado em produção; o `tests/conftest.py` desliga (o modelo roteirizado dos testes seria consumido); testes do classificador injetam o modelo.
7. **Teste do daemon "nuclear negado"** virou o CA-08: `rm -rf` no espaço do usuário agora é reversível e roda; o cenário usa `mkfs.ext4` e verifica a pendência na Inbox.
8. Ação polkit própria e presença por voz ficam como estavam na Sprint 1.

### Validação
- Suíte: 2438 testes, cobertura 93%, `ruff` e `mypy` limpos; lab 28/28.
- Novos: `test_bands.py`, `test_classifier.py`, `test_reversibility.py`, `test_grants.py`; `test_security_audit.py` com blocklist em `full` (8 variantes), Nuclear com senha errada e certa (PAM falso), filho que não sobe, Inbox sem humano e CA-06 ponta a ponta; `test_daemon.py` com CA-08 (Nuclear e Presença viram pendência, `rm` reversível roda); lab `test_bands.py` (overlay de Presença, aprovação de plano com passos, linha do lixo).
- **CA-06 ✅, CA-07 ✅ automático (diálogo polkit no GNOME pendente do Senhor, como na Sprint 1), CA-08 ✅.**
