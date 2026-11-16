# Sprint — v0.5.2 Sprint 1: Instalação sem venv, atualização e reversão

> **Status:** ✅ Implementada em 15/11/2026 · **ADR:** 044 · **CA:** CA-01, CA-02

## Objetivo
`orion` funciona em qualquer terminal sem ativar a venv; atualizar e reverter são um comando.

## Escopo
1. `src/orion/install.py`: layout (`~/.local/share/orion/{versions/<v>, current}`, `~/.local/bin/{orion, orion-agent}`), troca atômica do symlink (`os.replace` de um link temporário), poda para as duas últimas versões, rollback, leitura de tags `v*` (`git ls-remote --tags`), comparação de versões (PEP 440 via `packaging`), detecção de atalho ausente do PATH e de instalação duplicada.
2. `scripts/install.sh`: instala do checkout atual (`--dev` = editável) chamando `python -m orion.install`.
3. CLI: `orion update [--check] [--yes] [--rollback]`; sem TTY exige `--yes`.
4. PEP: `orion update`/`orion-agent update`/`install.sh` executados pelo agente são ação nuclear.
5. `/doctor`: linhas "Atalho" e "Instalação".

## Fora do escopo
PyPI, assinatura de pacotes, verificação automática pelo daemon.

## Testes
`tests/unit/test_install.py` com diretórios temporários e um repositório git local com duas tags (sem rede): instalar, atualizar, reverter, podar, PATH, duplicidade, nuclear no PEP.

## Registro de implementação (15/11/2026)
- `src/orion/install.py`, `scripts/install.sh`, `orion update [--check|--yes|--rollback]` em `cli.py`, linhas "Atalho" e "Instalação" no `/doctor`, padrões nucleares `orion update` e `python -m orion.install`.
- **Bug pego no teste de ponta a ponta:** a venv construída num diretório temporário e depois movida guarda caminhos absolutos antigos nos scripts. Agora a construção é no lugar final; reinstalar a mesma versão guarda a anterior e a restaura em caso de falha.
- Validação: `scripts/install.sh --dev` num HOME isolado; `orion --version` e `orion-agent --version` rodam com `env -i` sem venv.
- **Desvio:** o padrão nuclear para `install.sh` foi descartado (pegaria scripts de outros projetos); o agente rodando `install.sh` continua exigindo aprovação de nível 3.
- **Desvio:** `prune` mantém a atual e a anterior; sem parâmetro `keep`.
