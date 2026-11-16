# Sprint — v0.5.3 Sprint 2: Classificador e reversibilidade

> **Status:** 📋 Aguardando comando de início · **ADRs:** 046, 047 · **Achados:** G-04, G-10 · **CA:** CA-06 a CA-08

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
