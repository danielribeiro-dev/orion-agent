"""Faixas por raio de destruição e reversibilidade (ADR-046, v0.5.3 Sprint 2).

O PEP deixa de decidir por tool (LEVEL_0 a 3) e passa a decidir pelo que a ação pode destruir e
se o ORION consegue desfazê-la:

* ``LIVRE``: leitura, web, escrita reversível no escopo do usuário, comandos de leitura.
* ``CLASSIFICADA``: o resto (comando desconhecido, escrita fora do escopo, MCP mutante, ``sudo``
  não destrutivo, deleção com snapshot). Decidida pelo classificador em dois estágios.
* ``PRESENCA``: alto risco desfazível só com esforço (push para branch protegida, envio de dados a
  host novo com a sessão contaminada, units do sistema, ``docker system prune``...).
* ``NUCLEAR``: irreversível que o ORION não consegue desfazer. Exige presença verificada.
* **Blocklist**: nunca roda, em nenhum modo.

Tool sem faixa declarada é ``NUCLEAR`` (deny by default). Este módulo só lê o sistema de arquivos
para resolver symlinks e listar os dispositivos montados na raiz (``/proc/self/mounts``); quem
mede tamanho e copia é ``reversibility.py``.
"""

from __future__ import annotations

import contextlib
import fnmatch
import functools
import os
import re
import shlex
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from enum import IntEnum
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from orion.governance.paths import Zone, zone_of
from orion.governance.permissions import ActionLevel, WorkspaceScope

# ---------------------------------------------------------------------------
# Faixas
# ---------------------------------------------------------------------------


class Band(IntEnum):
    """Raio de destruição, do livre ao irreversível."""

    LIVRE = 0
    CLASSIFICADA = 1
    PRESENCA = 2
    NUCLEAR = 3

    @property
    def label(self) -> str:
        return _BAND_LABELS[self]

    def up(self) -> Band:
        """Uma faixa acima (alvo que o parser não resolve), no máximo Nuclear."""
        return Band(min(int(self) + 1, int(Band.NUCLEAR)))


_BAND_LABELS = {
    Band.LIVRE: "livre",
    Band.CLASSIFICADA: "classificada",
    Band.PRESENCA: "presença",
    Band.NUCLEAR: "nuclear",
}

OpKind = Literal["delete", "overwrite", "git_tree", "git_clean"]


@dataclass(frozen=True)
class DestructiveOp:
    """Deleção ou sobrescrita que o motor de reversibilidade fotografa antes de rodar.

    ``targets`` são caminhos já expandidos (``~``), relativos ao ``cwd`` quando não absolutos.
    ``git_tree`` (reset --hard, checkout -- ., restore) usa ``git stash create``; ``git_clean``
    guarda os arquivos que ``git clean -n`` com as mesmas flags listaria.
    """

    kind: OpKind
    targets: tuple[str, ...] = ()
    cwd: str | None = None
    git_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class BandVerdict:
    """Faixa de uma ação e por quê."""

    band: Band
    reason: str
    rule: str
    blocked: bool = False
    mutates: bool = True
    ops: tuple[DestructiveOp, ...] = ()
    unresolved: bool = False
    outbound_hosts: tuple[str, ...] = ()
    sudo: bool = False
    #: Classificada que as regras determinísticas já aprovam (reversível no escopo).
    stage1_allow: bool = False

    def raised(self, band: Band, reason: str, rule: str) -> BandVerdict:
        """Este veredito com a faixa elevada a *band* (nunca rebaixa)."""
        if band <= self.band:
            return self
        return replace(self, band=band, reason=reason, rule=rule, stage1_allow=False)


def _merge(verdicts: Iterable[BandVerdict]) -> BandVerdict:
    """Comando composto: a faixa é a do segmento mais perigoso; ops e flags se somam."""
    items = list(verdicts)
    if not items:
        return BandVerdict(Band.LIVRE, "comando vazio", "empty", mutates=False)
    worst = max(items, key=lambda v: (v.blocked, int(v.band)))
    return replace(
        worst,
        blocked=any(v.blocked for v in items),
        mutates=any(v.mutates for v in items),
        ops=tuple(op for v in items for op in v.ops),
        unresolved=any(v.unresolved for v in items),
        outbound_hosts=tuple(dict.fromkeys(h for v in items for h in v.outbound_hosts)),
        sudo=any(v.sudo for v in items),
        stage1_allow=all(v.stage1_allow or v.band == Band.LIVRE for v in items)
        and worst.band <= Band.CLASSIFICADA,
    )


# ---------------------------------------------------------------------------
# Faixas declaradas por tool
# ---------------------------------------------------------------------------

#: Faixa base de cada tool nativa. Escritas e ``run_command`` são refinadas pelos parâmetros.
TOOL_BANDS: dict[str, Band] = {
    "read_file": Band.LIVRE,
    "search_files": Band.LIVRE,
    "glob": Band.LIVRE,
    "grep": Band.LIVRE,
    "bash_output": Band.LIVRE,
    "inspect_environment": Band.LIVRE,
    "recall": Band.LIVRE,
    "use_skill": Band.LIVRE,
    "web_fetch": Band.LIVRE,
    "web_search": Band.LIVRE,
    "todo_write": Band.LIVRE,
    "ask_user": Band.LIVRE,
    "enter_plan_mode": Band.LIVRE,
    "exit_plan_mode": Band.LIVRE,
    "task": Band.LIVRE,
    "task_create": Band.LIVRE,
    "task_list": Band.LIVRE,
    "task_get": Band.LIVRE,
    "send_message": Band.LIVRE,
    "schedule_list": Band.LIVRE,
    "presence_rule_list": Band.LIVRE,
    "undo_last": Band.LIVRE,
    # Sessões (ADR-051): abrir/trocar thread só mexe no transcript do ORION.
    "session_branch": Band.LIVRE,
    "session_switch": Band.LIVRE,
    # Memória do ORION: nasce PROVISÓRIA e nada é apagado (superado aponta o sucessor).
    "memorize": Band.LIVRE,
    "deprecate_fact": Band.LIVRE,
    # Processos do próprio ORION.
    "kill_shell": Band.LIVRE,
    "task_stop": Band.LIVRE,
    # Escritas: Livre no escopo; o caminho decide (``_write_verdict``).
    "write_file": Band.LIVRE,
    "edit_file": Band.LIVRE,
    "notebook_edit": Band.LIVRE,
    # Comando: decidido segmento a segmento (``classify_command``).
    "run_command": Band.CLASSIFICADA,
    # Fato CONFIRMED só o Senhor promove (ADR-027).
    "record_decision": Band.PRESENCA,
    # Trabalho sem humano e como o ORION alcança o Senhor.
    "daemon_control": Band.PRESENCA,
    "schedule_create": Band.PRESENCA,
    "schedule_delete": Band.PRESENCA,
    "presence_rule_create": Band.PRESENCA,
    "presence_rule_delete": Band.PRESENCA,
}

_READ_ONLY_TOOLS = frozenset(
    {
        "read_file", "search_files", "glob", "grep", "bash_output", "inspect_environment",
        "recall", "use_skill", "web_fetch", "web_search", "task_list", "task_get",
        "schedule_list", "presence_rule_list", "todo_write", "ask_user", "enter_plan_mode",
        "exit_plan_mode", "task", "task_create", "send_message", "session_branch", "session_switch",
    }
)
WRITE_TOOLS = frozenset({"write_file", "edit_file", "notebook_edit"})
_PATH_READ_TOOLS = frozenset({"read_file", "grep", "search_files", "glob"})


def _is_credential(path: Path, ctx: BandContext) -> bool:
    """Chaves e credenciais do Senhor: leitura não é Livre (o conteúdo iria ao provedor)."""
    from orion.governance.paths import is_key_path, is_sensitive_path

    raw = str(path)
    if is_key_path(raw, ctx.home):
        return True
    credentials = (".netrc", ".pgpass", ".git-credentials", ".config/git/credentials", ".docker/config.json", ".kube/config", ".aws/credentials")
    try:
        rel = path.resolve().relative_to(ctx.home.resolve()).as_posix()
    except (ValueError, OSError):
        return False
    return is_sensitive_path(raw, ctx.home) and any(rel == c or rel.startswith(c + "/") for c in credentials)

_DYNAMIC_BANDS: dict[str, Band] = {}


def register_tool_band(tool_name: str, band: Band) -> None:
    """Declara a faixa de uma tool descoberta em tempo de execução (ex.: MCP)."""
    _DYNAMIC_BANDS[tool_name] = band


def unregister_tool_bands(prefix: str) -> None:
    for key in [k for k in _DYNAMIC_BANDS if k.startswith(prefix)]:
        del _DYNAMIC_BANDS[key]


def tool_band(tool_name: str) -> Band | None:
    """Faixa declarada de *tool_name*; None quando não há (vira Nuclear no PEP).

    Tools MCP registradas com nível (``register_tool_level``) herdam a faixa dele: leitura é
    Livre e mutante é Classificada.
    """
    if tool_name in TOOL_BANDS:
        return TOOL_BANDS[tool_name]
    if tool_name in _DYNAMIC_BANDS:
        return _DYNAMIC_BANDS[tool_name]
    from orion.governance.permissions import _DYNAMIC_LEVELS, TOOL_LEVELS

    static = TOOL_LEVELS.get(tool_name)
    if static is not None and static <= ActionLevel.LEVEL_1:
        return Band.LIVRE  # declarada sem efeito colateral; mutante sem faixa continua Nuclear

    level = _DYNAMIC_LEVELS.get(tool_name)
    if level is None:
        return None
    return Band.LIVRE if level <= ActionLevel.LEVEL_1 else Band.CLASSIFICADA


def is_external_content_tool(tool_name: str) -> bool:
    """Tools cujo resultado é conteúdo externo (contamina a sessão, ADR-049)."""
    return tool_name in ("web_fetch", "web_search") or tool_name.startswith("mcp__")


# ---------------------------------------------------------------------------
# Contexto
# ---------------------------------------------------------------------------

DEFAULT_PROTECTED_BRANCHES = ("main", "master", "trunk", "production", "prod", "release", "release/*")


@dataclass
class BandContext:
    """O que a classificação precisa saber além da ação."""

    scope: WorkspaceScope
    home: Path = field(default_factory=Path.home)
    orion_home: Path | None = None
    cwd: Path = field(default_factory=Path.cwd)
    contaminated: bool = False
    known_hosts: frozenset[str] = frozenset()
    protected_branches: tuple[str, ...] = DEFAULT_PROTECTED_BRANCHES
    #: Branch atual de um repositório (None se não resolve). Injetável nos testes.
    current_branch: Callable[[Path], str | None] | None = None
    #: Dispositivos montados em ``/``, ``/boot``, ``/home`` (e o disco-pai). Injetável.
    root_devices: Callable[[], frozenset[str]] | None = None

    def zone(self, path: str | Path) -> Zone:
        target = self.resolve(path)
        if _GLOB.search(str(target)):
            # Glob: vale a zona da parte fixa do caminho; glob direto na raiz é sistema.
            fixed = Path(*[p for p in _fixed_prefix(target.parts)])
            if fixed == Path("/") or not fixed.parts:
                return Zone.SYSTEM
            target = fixed
        return zone_of(
            target,
            in_scope=self.scope.is_allowed(target),
            home=self.home,
            orion_home=self.orion_home or self.home / ".orion",
        )

    def resolve(self, path: str | Path) -> Path:
        candidate = Path(str(path)).expanduser()
        if str(path).startswith("~"):
            candidate = self.home / str(path)[1:].lstrip("/")
        if not candidate.is_absolute():
            candidate = self.cwd / candidate
        return candidate

    def is_protected_branch(self, branch: str) -> bool:
        return any(fnmatch.fnmatchcase(branch, pattern) for pattern in self.protected_branches)


_GLOB = re.compile(r"[*?\[]")


def _fixed_prefix(parts: tuple[str, ...]) -> list[str]:
    fixed: list[str] = []
    for part in parts:
        if _GLOB.search(part):
            break
        fixed.append(part)
    return fixed


# ---------------------------------------------------------------------------
# Blocklist (nunca roda, nem em ``full``)
# ---------------------------------------------------------------------------

_RM_RECURSIVE = r"(?:-[a-zA-Z]*[rR][a-zA-Z]*|--recursive)"
_ROOTLIKE = r"(?:/|/\*|/\.\*|~/?|~/\*|\$HOME/?|\$\{HOME\}/?|/home/?|/home/\*)"
_BLOCKLIST: list[tuple[str, re.Pattern[str]]] = [
    (
        "rm_root",
        re.compile(
            rf"\brm\s+(?:\S+\s+)*?{_RM_RECURSIVE}\s+(?:\S+\s+)*?['\"]?{_ROOTLIKE}['\"]?(?:\s|$|;|&|\|)"
        ),
    ),
    ("rm_root_flag", re.compile(r"\brm\b[^;&|]*--no-preserve-root")),
    ("fork_bomb", re.compile(r"(\w+|:)\s*\(\s*\)\s*\{[^}]*\1\s*\|\s*\1\s*&[^}]*\}\s*;?\s*\1")),
    ("chmod_root", re.compile(r"\bch(?:mod|own|grp)\s+(?:\S+\s+)*?-[a-zA-Z]*R[a-zA-Z]*\s+(?:\S+\s+)*?/(?:\s|$|;|&|\|)")),
    (
        "curl_sh_root",
        re.compile(
            r"\b(?:curl|wget)\b[^|;&]*\|\s*sudo\s+(?:-\S+\s+)*(?:ba|z|da|k|fi)?sh\b"
        ),
    ),
    ("curl_sh_root", re.compile(r"\bsudo\s+(?:-\S+\s+)*(?:ba|z|da)?sh\s+-c\s+['\"]?\$\((?:curl|wget)\b")),
    ("dev_overwrite_root", re.compile(r">\s*/dev/(?:sd[a-z]|nvme\d+n\d+|vd[a-z]|mmcblk\d+)\b")),
]


def blocklist_match(command: str, root_devices: frozenset[str] = frozenset()) -> str | None:
    """Nome da regra da blocklist que *command* casa, ou None."""
    text = " ".join(command.split())
    for name, pattern in _BLOCKLIST:
        if pattern.search(text):
            return name
    if root_devices:
        for device in _device_args(text):
            if device in root_devices and re.search(r"\b(mkfs(?:\.\w+)?|dd|wipefs|blkdiscard)\b", text):
                return "format_root_device"
    return None


def _device_args(text: str) -> list[str]:
    found = re.findall(r"/dev/[\w/.-]+", text)
    return [d.rstrip(".,;") for d in found]


@functools.lru_cache(maxsize=1)
def mounted_root_devices() -> frozenset[str]:
    """Dispositivos de ``/``, ``/boot``, ``/boot/efi`` e ``/home`` e seus discos-pai."""
    devices: set[str] = set()
    try:
        lines = Path("/proc/self/mounts").read_text(encoding="utf-8").splitlines()
    except OSError:
        return frozenset()
    for line in lines:
        parts = line.split()
        if len(parts) < 2 or parts[1] not in ("/", "/boot", "/boot/efi", "/home"):
            continue
        dev = parts[0]
        if not dev.startswith("/dev/"):
            continue
        devices.add(dev)
        with contextlib.suppress(OSError):
            devices.add(os.path.realpath(dev))
        devices.update(_parent_disks(dev))
    return frozenset(devices)


def _parent_disks(dev: str) -> set[str]:
    parents: set[str] = set()
    for candidate in (dev, os.path.realpath(dev)):
        match = re.match(r"(/dev/(?:nvme\d+n\d+|mmcblk\d+))p\d+$", candidate)
        if match:
            parents.add(match.group(1))
        match = re.match(r"(/dev/(?:sd|vd|xvd|hd)[a-z]+)\d+$", candidate)
        if match:
            parents.add(match.group(1))
    return parents


# ---------------------------------------------------------------------------
# Tokenização conservadora de shell
# ---------------------------------------------------------------------------

_OPERATORS = frozenset({";", "&&", "||", "|", "&", "|&", "\n"})
_REDIRECTS = frozenset({">", ">>", ">|", "&>", "&>>", "1>", "2>", "1>>", "2>>", "<", "<<", "<<<"})
_OPAQUE = re.compile(r"\$\(|`|<\(|>\(")


@dataclass
class _Segment:
    argv: list[str]
    redirects: list[tuple[str, str]]
    piped_in: bool = False


def _tokenize(command: str) -> list[_Segment] | None:
    """Segmentos simples do comando; None quando o shell não é parseável com segurança."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>")
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        tokens = list(lexer)
    except ValueError:
        return None
    segments: list[_Segment] = []
    current = _Segment([], [])
    pending_redirect: str | None = None
    previous_pipe = False
    for raw in tokens:
        token = raw
        if pending_redirect is not None:
            current.redirects.append((pending_redirect, token))
            pending_redirect = None
            continue
        fd_redirect = re.fullmatch(r"(\d?)([<>]{1,2}|>\|)", token)
        if token in _REDIRECTS or fd_redirect:
            if current.argv and re.fullmatch(r"\d", current.argv[-1] or "") and token.startswith(">"):
                current.argv.pop()  # "2" de "2>" virou token próprio
            pending_redirect = token
            continue
        if token.startswith(">&") or token.endswith(">&") or token in (">&", "<&"):
            continue  # 2>&1 e afins: duplicação de descritor, sem arquivo
        if token in _OPERATORS or set(token) <= set(";&|") and token:
            if current.argv or current.redirects:
                segments.append(current)
            previous_pipe = token in ("|", "|&")
            current = _Segment([], [], piped_in=previous_pipe)
            continue
        current.argv.append(token)
    if pending_redirect is not None:
        return None
    if current.argv or current.redirects:
        segments.append(current)
    return segments


_WRAPPERS = frozenset({"nice", "nohup", "time", "command", "builtin", "exec", "stdbuf", "ionice", "timeout"})


def _unwrap(argv: list[str]) -> tuple[list[str], bool]:
    """Remove atribuições de ambiente, ``sudo``/``doas`` e wrappers; devolve (argv, sudo)."""
    sudo = False
    args = list(argv)
    changed = True
    while args and changed:
        changed = False
        while args and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", args[0]):
            args.pop(0)
            changed = True
        if args and os.path.basename(args[0]) in ("sudo", "doas", "pkexec"):
            sudo = True
            args.pop(0)
            while args and args[0].startswith("-"):
                flag = args.pop(0)
                if flag in ("-u", "-g", "-C", "-h", "-p", "-r", "-t", "-U", "-D") and args:
                    args.pop(0)
            changed = True
        if args and os.path.basename(args[0]) == "env":
            rest = args[1:]
            while rest and (rest[0].startswith("-") or "=" in rest[0]):
                rest.pop(0)
            if not rest:
                break  # ``env`` sozinho imprime o ambiente (pode ter chaves): fica como programa
            args = rest
            changed = True
        if args and os.path.basename(args[0]) in _WRAPPERS:
            name = os.path.basename(args.pop(0))
            while args and args[0].startswith("-"):
                args.pop(0)
            if name == "timeout" and args:
                args.pop(0)  # duração
            changed = True
    return args, sudo


def _has_glob_or_var(target: str) -> bool:
    return bool(re.search(r"[$`{}]", target)) or (target.startswith("~") and not re.match(r"~(/|$)", target))


def _split_flags(args: list[str]) -> tuple[set[str], list[str]]:
    """(flags curtas e longas, operandos), respeitando ``--``."""
    flags: set[str] = set()
    operands: list[str] = []
    end = False
    for arg in args:
        if end or not arg.startswith("-") or arg == "-":
            operands.append(arg)
            continue
        if arg == "--":
            end = True
            continue
        if arg.startswith("--"):
            flags.add(arg.split("=", 1)[0])
        else:
            flags.update(f"-{ch}" for ch in arg[1:])
    return flags, operands


# ---------------------------------------------------------------------------
# Tabelas de comandos
# ---------------------------------------------------------------------------

_READ_PROGRAMS = frozenset(
    {
        "ls", "ll", "la", "cat", "bat", "batcat", "head", "tail", "less", "more", "wc", "pwd",
        "echo", "printf", "which", "whereis", "type", "file", "stat", "du", "df", "tree", "grep",
        "egrep", "fgrep", "rg", "ag", "fd", "fdfind", "sort", "uniq", "cut", "tr", "diff",
        "cmp", "comm", "date", "cal", "whoami", "id", "groups", "uname", "hostname", "ps",
        "pgrep", "free", "uptime", "lsblk", "lscpu", "lsusb", "lspci", "jq", "yq", "basename",
        "dirname", "realpath", "readlink", "true", "false", "test", "[", "sleep", "seq", "nproc",
        "column", "nl", "fold", "md5sum", "sha1sum", "sha256sum", "base64", "xxd", "od", "hexdump",
        "strings", "man", "tldr", "locale", "getent", "ldd", "dpkg-query", "lsof", "ss",
        "ping", "dig", "host", "nslookup", "tput", "clear", "history", "zcat", "zless",
        "pytest", "mypy", "tsc", "shellcheck", "pyright", "cd", "pushd", "popd", "dirs",
    }
)

_GIT_READ = frozenset(
    {
        "status", "log", "diff", "show", "rev-parse", "describe", "blame", "ls-files", "ls-tree",
        "grep", "shortlog", "reflog", "cat-file", "rev-list", "merge-base", "whatchanged",
        "show-ref", "for-each-ref", "name-rev", "count-objects", "fsck", "version", "help",
    }
)
_GIT_LOCAL_REVERSIBLE = frozenset({"add", "commit", "fetch", "switch", "init", "clone", "worktree"})

_ESSENTIAL_PACKAGES = frozenset(
    {
        "apt", "dpkg", "libc6", "libc-bin", "systemd", "systemd-sysv", "sudo", "sudo-rs", "bash",
        "coreutils", "util-linux", "login", "passwd", "init", "base-files", "base-passwd",
        "dash", "grub-common", "grub2-common", "grub-pc", "grub-efi-amd64", "grub-efi-amd64-signed",
        "shim-signed", "linux-generic", "linux-image-generic", "network-manager", "netplan.io",
        "gnome-shell", "ubuntu-desktop", "ubuntu-minimal", "ubuntu-standard", "gdm3", "polkitd",
        "policykit-1", "openssh-server", "python3", "perl-base", "tar", "gzip", "mount",
        "e2fsprogs", "initramfs-tools", "udev", "dbus", "kmod", "ca-certificates", "glibc",
        "kernel", "linux", "pacman", "dnf", "rpm", "zypper",
    }
)
_PKG_MANAGERS = frozenset({"apt", "apt-get", "aptitude", "dpkg", "dnf", "yum", "pacman", "zypper", "snap", "flatpak", "rpm"})
_PKG_REMOVE = frozenset({"remove", "purge", "erase", "-r", "-P", "-R", "-Rs", "-Rns", "-Rsc", "uninstall", "--remove", "--purge"})
_PKG_READ = frozenset({"list", "search", "show", "policy", "info", "-Q", "-Ss", "-Si", "-Qi", "-l", "-L", "-s", "madison", "depends", "rdepends", "--list", "-Ql"})

_DISK_PROGRAMS = frozenset({"mkfs", "wipefs", "parted", "fdisk", "sfdisk", "gdisk", "sgdisk", "cfdisk", "blkdiscard", "mkswap", "cryptsetup", "shred", "wipe", "zerofree"})

_OUTBOUND_PROGRAMS = frozenset({"scp", "sftp", "ftp", "nc", "ncat", "netcat", "socat", "telnet", "rsync", "ssh"})
_SECRET_HINTS = re.compile(
    r"(\.ssh/|id_rsa|id_ed25519|id_ecdsa|\.gnupg|\.aws/credentials|\.netrc|\.pgpass|\.git-credentials|"
    r"\.docker/config\.json|\.kube/config|keyrings|\.orion/\.env|\.orion/secrets|\.env\b|_api_key\b)"
)
_ORION_SECRET = re.compile(r"\.orion/(\.env|secrets\b|anthropic_api_key|openrouter_api_key)")

_INTERPRETERS = frozenset({"python", "python3", "node", "deno", "bun", "bash", "sh", "zsh", "dash", "fish", "perl", "ruby", "php", "lua"})
_SAFE_PY_MODULES = frozenset({"pytest", "mypy", "ruff", "pyright", "pip"})

_GENERIC_CLASSIFIED = frozenset(
    {
        "npm", "npx", "yarn", "pnpm", "pip", "pip3", "uv", "pipx", "cargo", "go", "make", "cmake",
        "docker-compose", "podman", "kubectl", "terraform", "ansible", "brew", "gem", "composer",
        "mvn", "gradle", "dotnet", "tox", "nox", "poetry", "pdm", "hatch", "kill", "pkill",
        "killall", "xargs", "tee", "install", "patch", "tar", "zip", "unzip", "gzip", "gunzip",
        "xz", "7z", "ln", "chmod", "chown", "chgrp", "mkdir", "touch", "cp", "rsync", "curl", "wget",
        "env", "printenv", "export", "source", ".", "eval", "awk", "gawk", "ruff", "black",
        "isort", "eslint", "prettier",
    }
)


# ---------------------------------------------------------------------------
# Classificação
# ---------------------------------------------------------------------------


def _livre(reason: str, rule: str, *, mutates: bool = False) -> BandVerdict:
    return BandVerdict(Band.LIVRE, reason, rule, mutates=mutates)


def _classified(reason: str, rule: str, **kw: object) -> BandVerdict:
    return BandVerdict(Band.CLASSIFICADA, reason, rule, **kw)  # type: ignore[arg-type]


def _band_for_zone(zone: Zone) -> tuple[Band, bool, str]:
    """(faixa, bloqueado, regra) de uma escrita/deleção reversível numa zona."""
    if zone in (Zone.SECRET, Zone.GOVERNANCE):
        return Band.NUCLEAR, True, f"zone:{zone.value}"
    if zone in (Zone.KEYS, Zone.SYSTEM):
        return Band.NUCLEAR, False, f"zone:{zone.value}"
    if zone == Zone.SENSITIVE:
        return Band.PRESENCA, False, "zone:sensitive"
    if zone == Zone.OUTSIDE:
        return Band.CLASSIFICADA, False, "zone:outside"
    return Band.LIVRE, False, "zone:scope"


def classify_action(tool: str, params: dict[str, object], ctx: BandContext) -> BandVerdict:
    """Faixa da chamada de *tool* com *params*."""
    base = tool_band(tool)
    if base is None:
        return BandVerdict(Band.NUCLEAR, f"tool '{tool}' sem faixa declarada (deny by default)", "undeclared_tool")
    if tool == "run_command":
        command = str(params.get("command", "") or "")
        cwd = str(params.get("cwd", "") or "")
        local = replace(ctx, cwd=ctx.resolve(cwd)) if cwd else ctx
        return classify_command(command, local)
    if tool in WRITE_TOOLS:
        return _write_verdict(str(params.get("path", "") or params.get("notebook_path", "") or ""), ctx)
    if tool in _PATH_READ_TOOLS:
        raw = str(params.get("path", "") or "")
        if raw and _is_credential(ctx.resolve(raw), ctx):
            return BandVerdict(Band.CLASSIFICADA, f"leitura de chave/credencial: {raw}", "read:credential", mutates=False)
    if tool == "web_fetch":
        return _web_fetch_verdict(str(params.get("url", "") or ""), ctx)
    mutates = tool not in _READ_ONLY_TOOLS
    if base == Band.LIVRE:
        return BandVerdict(Band.LIVRE, f"{tool}: sem efeito destrutivo", f"tool:{tool}", mutates=mutates)
    return BandVerdict(base, f"{tool}: faixa {base.label} declarada", f"tool:{tool}", mutates=True)


def _write_verdict(path: str, ctx: BandContext) -> BandVerdict:
    if not path:
        return _classified("escrita sem caminho", "write:no_path", mutates=True)
    zone = ctx.zone(path)
    band, blocked, rule = _band_for_zone(zone)
    reasons = {
        Zone.SECRET: "segredo do ORION",
        Zone.GOVERNANCE: "governança do ORION",
        Zone.KEYS: "chaves do Senhor (~/.ssh, ~/.gnupg, chaveiro)",
        Zone.SYSTEM: "arquivo do sistema",
        Zone.SENSITIVE: "arquivo sensível do Senhor (login, autostart, credenciais)",
        Zone.OUTSIDE: "escrita fora do espaço do usuário",
        Zone.SCOPE: "escrita reversível no espaço do usuário",
    }
    return BandVerdict(band, f"{reasons[zone]}: {path}", rule, blocked=blocked, mutates=True)


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _web_fetch_verdict(url: str, ctx: BandContext) -> BandVerdict:
    host = _host(url)
    carries_data = "?" in url or "#" in url
    if ctx.contaminated and carries_data and host and host not in ctx.known_hosts:
        return BandVerdict(
            Band.PRESENCA,
            f"sessão contaminada enviando dados a host novo ({host})",
            "exfil:new_host",
            mutates=False,
            outbound_hosts=(host,),
        )
    return BandVerdict(Band.LIVRE, "leitura web", "tool:web_fetch", mutates=False, outbound_hosts=(host,) if host else ())


def classify_command(command: str, ctx: BandContext) -> BandVerdict:
    """Faixa de um comando de shell (composto: a do pior segmento)."""
    text = command.strip()
    if not text:
        return _livre("comando vazio", "empty")
    devices = ctx.root_devices() if ctx.root_devices is not None else mounted_root_devices()
    blocked = blocklist_match(text, devices)
    if blocked is not None:
        return BandVerdict(Band.NUCLEAR, f"blocklist: {blocked}", f"blocklist:{blocked}", blocked=True)
    if _ORION_SECRET.search(text):
        return BandVerdict(Band.NUCLEAR, "toca segredos do ORION", "secret", blocked=True)
    opaque = bool(_OPAQUE.search(text))
    segments = _tokenize(text.replace("\n", " ; "))
    if segments is None:
        return _classified("shell não parseável com segurança", "unparseable", unresolved=True)
    for seg in segments:
        normalized = blocklist_match(" ".join(seg.argv), devices)
        if normalized is not None:
            return BandVerdict(Band.NUCLEAR, f"blocklist: {normalized}", f"blocklist:{normalized}", blocked=True)
    verdicts: list[BandVerdict] = []
    local = ctx
    lost_cwd = False
    for seg in segments:
        argv, _sudo = _unwrap(seg.argv)
        if argv and argv[0] in ("cd", "pushd"):
            target = argv[1] if len(argv) > 1 else "~"
            if _has_glob_or_var(target) or target == "-":
                lost_cwd = True
            else:
                local = replace(local, cwd=local.resolve(target))
        verdict = _segment_verdict(seg, local)
        if lost_cwd and verdict.ops:
            verdict = replace(verdict, unresolved=True, stage1_allow=False)
        verdicts.append(verdict)
    merged = _merge(verdicts)
    if opaque:
        merged = replace(merged, unresolved=True, stage1_allow=False)
        merged = merged.raised(Band.CLASSIFICADA, "substituição de comando: conteúdo opaco", "opaque")
    outbound = merged.outbound_hosts or any(v.rule.startswith("outbound") for v in verdicts)
    if outbound and _SECRET_HINTS.search(text):
        merged = merged.raised(Band.NUCLEAR, "envio de segredo para fora", "exfil:secret")
    elif outbound and ctx.contaminated and any(h not in ctx.known_hosts for h in merged.outbound_hosts or ("?",)):
        merged = merged.raised(Band.PRESENCA, "sessão contaminada enviando dados a host novo", "exfil:new_host")
    if any(seg.piped_in for seg in segments) and any(v.ops for v in verdicts):
        merged = replace(merged, unresolved=True, stage1_allow=False)
    return merged


def _segment_verdict(seg: _Segment, ctx: BandContext) -> BandVerdict:
    argv, sudo = _unwrap(seg.argv)
    verdict = _program_verdict(argv, ctx, piped_in=seg.piped_in)
    verdict = _apply_redirects(verdict, seg.redirects, ctx)
    if sudo:
        verdict = replace(verdict, sudo=True, stage1_allow=False, mutates=True)
        if verdict.ops:
            verdict = verdict.raised(Band.NUCLEAR, "sudo com deleção/sobrescrita (sem snapshot como root)", "sudo:destructive")
        verdict = verdict.raised(Band.CLASSIFICADA, "sudo não destrutivo", "sudo")
    return verdict


def _apply_redirects(verdict: BandVerdict, redirects: list[tuple[str, str]], ctx: BandContext) -> BandVerdict:
    for op, target in redirects:
        if op.startswith("<"):
            continue
        if target in ("/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty") or target.startswith("&"):
            continue
        if target.startswith("/dev/"):
            verdict = verdict.raised(Band.NUCLEAR, f"escrita direta em dispositivo {target}", "dev_write")
            continue
        if _has_glob_or_var(target):
            verdict = replace(verdict.raised(Band.CLASSIFICADA, "redirecionamento para alvo opaco", "redirect:opaque"), unresolved=True)
            continue
        zone = ctx.zone(target)
        band, blocked, rule = _band_for_zone(zone)
        exists = ctx.resolve(target).exists()
        ops = verdict.ops + ((DestructiveOp("overwrite", (str(ctx.resolve(target)),), str(ctx.cwd)),) if exists else ())
        merged = replace(verdict, blocked=verdict.blocked or blocked, mutates=True, ops=ops)
        if band > merged.band:
            merged = merged.raised(band, f"redirecionamento para {target}", f"redirect:{rule}")
        elif merged.band == Band.LIVRE and exists:
            merged = replace(merged, band=Band.CLASSIFICADA, reason=f"sobrescreve {target} (com snapshot)", rule="redirect:overwrite", stage1_allow=zone == Zone.SCOPE)
        verdict = merged
    return verdict


def _program_verdict(argv: list[str], ctx: BandContext, *, piped_in: bool) -> BandVerdict:
    if not argv:
        return _livre("só atribuições", "assign")
    program = os.path.basename(argv[0])
    args = argv[1:]
    if program.startswith("mkfs") or program in _DISK_PROGRAMS:
        return BandVerdict(Band.NUCLEAR, f"{program}: destrói dados em disco", f"disk:{program}")
    handler = _HANDLERS.get(program)
    if handler is not None:
        return handler(program, args, ctx, piped_in)
    if program in _READ_PROGRAMS:
        risky = _read_program_risk(program, args, ctx)
        if risky is not None:
            return risky
        return _livre(f"{program}: leitura", f"read:{program}")
    if program in ("bash", "sh", "zsh", "dash") and len(args) >= 2 and args[0] in ("-c", "-lc", "-ec"):
        return classify_command(args[1], ctx)
    if program == "xargs":
        inner = args[:]
        while inner and inner[0].startswith("-"):
            flag = inner.pop(0)
            if flag in ("-I", "-n", "-P", "-d", "-L", "-s", "-E", "-a") and inner:
                inner.pop(0)
        verdict = _program_verdict(inner or ["echo"], ctx, piped_in=True)
        ops = verdict.ops or ((DestructiveOp("delete", (), str(ctx.cwd)),) if verdict.mutates and verdict.band > Band.LIVRE else ())
        return replace(verdict.raised(Band.CLASSIFICADA, "xargs: alvos vindos da entrada", "xargs"), unresolved=True, stage1_allow=False, ops=ops)
    if program in _INTERPRETERS:
        return _interpreter_verdict(program, args)
    if re.fullmatch(r"python\d(\.\d+)?", program):
        return _interpreter_verdict("python", args)
    if program in ("orion", "orion-agent") and args[:1] == ["update"]:
        return BandVerdict(Band.NUCLEAR, "troca o código instalado do ORION (ADR-044)", "orion_update")
    if program in ("orion", "orion-agent"):
        return _classified("comando do ORION", "orion")
    if program in _GENERIC_CLASSIFIED:
        return _generic_verdict(program, args, ctx)
    return _classified(f"comando desconhecido: {program}", "unknown")


#: Flags que fazem um programa "de leitura" escrever arquivo ou executar outro programa.
_READ_WRITE_FLAGS: dict[str, frozenset[str]] = {
    "sort": frozenset({"-o", "--output"}),
    "tree": frozenset({"-o"}),
    "rg": frozenset({"--pre"}),
    "xxd": frozenset({"-r", "--revert"}),
    "fd": frozenset({"-x", "--exec", "-X", "--exec-batch"}),
    "fdfind": frozenset({"-x", "--exec", "-X", "--exec-batch"}),
    "date": frozenset({"-s", "--set"}),
    "hostname": frozenset({"-b", "-F", "--file"}),
}


def _read_program_risk(program: str, args: list[str], ctx: BandContext) -> BandVerdict | None:
    """Leitura que na verdade escreve, executa ou abre credencial: deixa de ser Livre."""
    flags = {a.split("=", 1)[0] for a in args if a.startswith("-")}
    risky = _READ_WRITE_FLAGS.get(program, frozenset())
    if flags & risky or any(a.startswith(tuple(f + "=" for f in risky if f.startswith("--"))) for a in args):
        return _classified(f"{program} com {sorted(flags & risky) or 'saída/execução'}", f"read_write:{program}", mutates=True)
    if program == "uniq" and len([a for a in args if not a.startswith("-")]) >= 2:
        return _classified("uniq com arquivo de saída", "read_write:uniq", mutates=True)
    for arg in args:
        if arg.startswith("-") or _has_glob_or_var(arg):
            continue
        if ("/" in arg or arg.startswith(".") or arg.startswith("~")) and _is_credential(ctx.resolve(arg), ctx):
            return BandVerdict(Band.CLASSIFICADA, f"{program} lê chave/credencial: {arg}", "read:credential", mutates=False)
    return None


_SED_EXEC_OR_WRITE = re.compile(r"(?:^|[;{}\s])[0-9,$/!]*\s*[ewWrR](?:\s|$)|s(.).*\1.*\1[gpiImM0-9]*[ew]")


# ── Handlers por programa ───────────────────────────────────────────────────


def _rm(program: str, args: list[str], ctx: BandContext, piped_in: bool) -> BandVerdict:
    flags, operands = _split_flags(args)
    if not operands:
        return _livre("rm sem alvo", "rm:noop") if not piped_in else _classified("rm via pipe", "rm:piped", unresolved=True)
    return _deletion(program, operands, ctx, kind="delete")


def _deletion(program: str, operands: list[str], ctx: BandContext, *, kind: OpKind) -> BandVerdict:
    unresolved = any(_has_glob_or_var(t) for t in operands)
    resolved = [str(ctx.resolve(t)) if not _has_glob_or_var(t) else t for t in operands]
    worst = Band.CLASSIFICADA
    blocked = False
    rule = f"{program}:snapshot"
    all_scope = True
    for target in operands:
        if _has_glob_or_var(target):
            all_scope = False
            continue
        zone = ctx.zone(target)
        band, is_blocked, zone_rule = _band_for_zone(zone)
        blocked = blocked or is_blocked
        if zone != Zone.SCOPE:
            all_scope = False
        if band > worst:
            worst, rule = band, f"{program}:{zone_rule}"
    verdict = BandVerdict(
        worst,
        f"{program} de {len(operands)} alvo(s) com snapshot" if worst == Band.CLASSIFICADA else f"{program} em zona protegida",
        rule,
        blocked=blocked,
        ops=(DestructiveOp(kind, tuple(resolved), str(ctx.cwd)),),
        unresolved=unresolved,
        stage1_allow=all_scope and not unresolved and worst == Band.CLASSIFICADA,
    )
    return verdict


def _mv_cp(program: str, args: list[str], ctx: BandContext, piped_in: bool) -> BandVerdict:
    flags, operands = _split_flags(args)
    if "-t" in flags or "--target-directory" in flags or len(operands) < 2:
        return _classified(f"{program} com alvo não resolvido", f"{program}:unresolved", unresolved=True)
    *sources, dest = operands
    if _has_glob_or_var(dest):
        return _classified(f"{program} para destino opaco", f"{program}:opaque", unresolved=True)
    dest_path = ctx.resolve(dest)
    overwritten: list[str] = []
    if dest_path.is_dir():
        for src in sources:
            if _has_glob_or_var(src):
                return _classified(f"{program} com origem opaca para pasta existente", f"{program}:opaque", unresolved=True)
            candidate = dest_path / Path(src.rstrip("/")).name
            if candidate.exists():
                overwritten.append(str(candidate))
    elif dest_path.exists():
        overwritten.append(str(dest_path))
    zones = [ctx.zone(dest)] + ([ctx.zone(s) for s in sources if not _has_glob_or_var(s)] if program == "mv" else [])
    worst_band, blocked, rule = Band.LIVRE, False, f"{program}:scope"
    for zone in zones:
        band, is_blocked, zone_rule = _band_for_zone(zone)
        blocked = blocked or is_blocked
        if band > worst_band:
            worst_band, rule = band, f"{program}:{zone_rule}"
    ops = (DestructiveOp("overwrite", tuple(overwritten), str(ctx.cwd)),) if overwritten else ()
    if worst_band == Band.LIVRE and overwritten:
        return BandVerdict(Band.CLASSIFICADA, f"{program} sobrescreve {len(overwritten)} arquivo(s) (com snapshot)", f"{program}:overwrite", ops=ops, stage1_allow=True)
    if worst_band == Band.LIVRE:
        return BandVerdict(Band.LIVRE, f"{program} no espaço do usuário", rule, mutates=True)
    return BandVerdict(worst_band, f"{program} envolve zona {rule}", rule, blocked=blocked, ops=ops)


def _sed(program: str, args: list[str], ctx: BandContext, piped_in: bool) -> BandVerdict:
    in_place = any(a == "-i" or a.startswith("-i") or a.startswith("--in-place") for a in args if a.startswith("-"))
    if program == "perl":
        in_place = any(re.fullmatch(r"-[a-zA-Z]*i\S*", a) for a in args)
        if not in_place:
            return _interpreter_verdict("perl", args)
    if not in_place:
        if program == "sed" and any(_SED_EXEC_OR_WRITE.search(a) for a in args if not a.startswith("-") or a.startswith("-e")):
            return _classified("sed com comando que executa ou escreve (e/w/r)", "sed:exec", mutates=True)
        return _livre(f"{program} sem -i", f"read:{program}")
    files: list[str] = []
    has_script_flag = any(a in ("-e", "--expression", "-f", "--file") for a in args)
    skip_next = False
    script_taken = has_script_flag
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg in ("-e", "--expression", "-f", "--file"):
            skip_next = True
            continue
        if arg.startswith("-"):
            continue
        if not script_taken:
            script_taken = True
            continue
        files.append(arg)
    if not files:
        return _classified(f"{program} -i sem arquivo resolvido", f"{program}:unresolved", unresolved=True)
    return _deletion(program, files, ctx, kind="overwrite")


def _truncate(program: str, args: list[str], ctx: BandContext, piped_in: bool) -> BandVerdict:
    _flags, operands = _split_flags(args)
    files = [o for o in operands if not re.fullmatch(r"[-+<>/%]?\d+[KMGTPkmgtp]?[Bb]?", o)]
    if not files:
        return _classified("truncate sem alvo", "truncate:unresolved", unresolved=True)
    return _deletion(program, files, ctx, kind="overwrite")


def _rmdir(program: str, args: list[str], ctx: BandContext, piped_in: bool) -> BandVerdict:
    _flags, operands = _split_flags(args)
    if not operands:
        return _livre("rmdir sem alvo", "rmdir:noop")
    return _deletion(program, operands, ctx, kind="delete")


def _dd(program: str, args: list[str], ctx: BandContext, piped_in: bool) -> BandVerdict:
    target = next((a[3:] for a in args if a.startswith("of=")), "")
    if not target:
        return _livre("dd para a saída padrão", "dd:stdout")
    if target.startswith("/dev/") and target not in ("/dev/null", "/dev/zero"):
        return BandVerdict(Band.NUCLEAR, f"dd sobre dispositivo {target}", "disk:dd")
    return _deletion("dd", [target], ctx, kind="overwrite") if ctx.resolve(target).exists() else _write_verdict(target, ctx)


def _find(program: str, args: list[str], ctx: BandContext, piped_in: bool) -> BandVerdict:
    if any(a in ("-delete",) for a in args):
        return _classified("find -delete: alvos só conhecidos na execução", "find:delete", unresolved=True, ops=(DestructiveOp("delete", (), str(ctx.cwd)),))
    if any(a in ("-exec", "-execdir", "-ok", "-okdir") for a in args):
        idx = next(i for i, a in enumerate(args) if a in ("-exec", "-execdir", "-ok", "-okdir"))
        inner = [a for a in args[idx + 1 :] if a not in (";", "+", "{}", "\\;")]
        inner_verdict = _program_verdict(inner, ctx, piped_in=False)
        if inner_verdict.band == Band.LIVRE and not inner_verdict.mutates:
            return _livre("find -exec de leitura", "find:exec_read")
        return replace(inner_verdict.raised(Band.CLASSIFICADA, "find -exec mutante", "find:exec"), unresolved=True, stage1_allow=False)
    if any(a.startswith("-fprint") or a.startswith("-fls") for a in args):
        return _classified("find escreve arquivo", "find:write", mutates=True)
    return _livre("find: leitura", "read:find")


def _git(program: str, args: list[str], ctx: BandContext, piped_in: bool) -> BandVerdict:
    rest = list(args)
    repo_cwd = ctx.cwd
    while rest and rest[0].startswith("-"):
        flag = rest.pop(0)
        if flag in ("-c", "--config-env") or flag.startswith("--exec-path"):
            # ``-c core.pager=...``/``core.sshCommand=...`` executam programas: nunca leitura.
            return _classified("git com configuração na linha de comando", "git:config_override")
        if flag in ("-C",) and rest:
            repo_cwd = ctx.resolve(rest.pop(0))
        elif flag in ("--git-dir", "--work-tree", "--namespace") and rest:
            rest.pop(0)
    if not rest:
        return _livre("git sem subcomando", "git:help")
    sub, sub_args = rest[0], rest[1:]
    local = replace(ctx, cwd=repo_cwd)
    flags, operands = _split_flags(sub_args)
    if sub in _GIT_READ:
        if any(a.startswith(("--output", "--ext-diff", "--textconv", "--upload-pack", "--exec")) for a in sub_args):
            return _classified(f"git {sub} que escreve ou executa", f"git:{sub}_exec", mutates=True)
        return _livre(f"git {sub}: leitura", f"git:{sub}")
    if sub == "branch":
        if flags & {"-d", "-D", "--delete", "-m", "-M", "--move", "-c", "-C", "-f", "--force"}:
            return _classified("git branch altera refs", "git:branch_mutate")
        if not operands or flags & {"-a", "-r", "-l", "--list", "-v", "-vv", "--show-current", "--contains", "--merged", "--no-merged"}:
            return _livre("git branch: leitura", "git:branch")
        return _livre("git branch nova", "git:branch_new", mutates=True)
    if sub == "tag" and not operands:
        return _livre("git tag: leitura", "git:tag")
    if sub == "remote" and (not operands or operands[0] in ("show", "get-url") or flags & {"-v", "--verbose"}):
        return _livre("git remote: leitura", "git:remote")
    if sub == "config" and flags & {"--get", "--list", "-l", "--get-all", "--get-regexp"}:
        return _livre("git config: leitura", "git:config_read")
    if sub == "stash":
        action = operands[0] if operands else "push"
        if action in ("list", "show"):
            return _livre("git stash: leitura", "git:stash_read")
        if action in ("drop", "clear"):
            return _classified("git stash drop/clear apaga trabalho guardado", "git:stash_drop")
        return _livre("git stash guarda o trabalho", "git:stash", mutates=True)
    if sub == "switch" and flags & {"--discard-changes", "-f", "--force"}:
        return _git_tree_op("switch", sub_args, local)
    if sub in _GIT_LOCAL_REVERSIBLE:
        return _livre(f"git {sub}: reversível", f"git:{sub}", mutates=True)
    if sub == "reset":
        if flags & {"--hard", "--merge", "--keep"}:
            return _git_tree_op("reset", sub_args, local)
        return _livre("git reset sem --hard: reversível", "git:reset_soft", mutates=True)
    if sub == "checkout":
        touches_paths = any((repo_cwd / o).exists() for o in operands if not _has_glob_or_var(o))
        if "--" in sub_args or operands[:1] == ["."] or flags & {"-f", "--force"} or touches_paths:
            return _git_tree_op("checkout", sub_args, local)
        if flags & {"-b", "-B"} or operands:
            return _livre("git checkout de branch", "git:checkout", mutates=True)
        return _livre("git checkout", "git:checkout", mutates=True)
    if sub == "restore":
        if flags & {"--staged", "-S"} and not flags & {"--worktree", "-W"}:
            return _livre("git restore --staged", "git:restore_staged", mutates=True)
        return _git_tree_op("restore", sub_args, local)
    if sub == "clean":
        if not flags & {"-f", "--force"} or flags & {"-n", "--dry-run"}:
            return _livre("git clean sem -f", "git:clean_dry")
        return BandVerdict(
            Band.CLASSIFICADA,
            "git clean com snapshot dos não rastreados",
            "git:clean",
            ops=(DestructiveOp("git_clean", (), str(repo_cwd), tuple(sub_args)),),
            stage1_allow=ctx.zone(repo_cwd) == Zone.SCOPE,
        )
    if sub == "push":
        return _git_push(sub_args, local)
    if sub in ("pull", "merge", "rebase", "cherry-pick", "revert", "am", "apply", "tag", "submodule", "remote", "config", "gc", "prune", "filter-branch", "update-ref", "replace", "notes", "bisect", "mv", "rm", "lfs", "sparse-checkout"):
        if sub == "filter-branch" or (sub == "update-ref" and flags & {"-d"}):
            return BandVerdict(Band.PRESENCA, f"git {sub} reescreve histórico", f"git:{sub}")
        return _classified(f"git {sub}", f"git:{sub}")
    return _classified(f"git {sub}", f"git:{sub}")


def _git_tree_op(sub: str, sub_args: list[str], ctx: BandContext) -> BandVerdict:
    return BandVerdict(
        Band.CLASSIFICADA,
        f"git {sub} descarta mudanças (com snapshot em refs/orion/undo)",
        f"git:{sub}",
        ops=(DestructiveOp("git_tree", (), str(ctx.cwd), (sub, *sub_args)),),
        stage1_allow=ctx.zone(ctx.cwd) == Zone.SCOPE,
    )


def _git_push(sub_args: list[str], ctx: BandContext) -> BandVerdict:
    flags, operands = _split_flags(sub_args)
    force = bool(flags & {"-f", "--force", "--force-with-lease", "--force-if-includes", "--mirror", "-d", "--delete", "--prune"})
    refspecs = operands[1:] if len(operands) > 1 else []
    if any(r.startswith("+") or r.startswith(":") for r in refspecs):
        force = True
    targets: list[str] = []
    for ref in refspecs:
        dest = ref.lstrip("+").split(":", 1)[-1]
        targets.append(dest.removeprefix("refs/heads/"))
    if not targets or flags & {"--all", "--mirror"}:
        branch = ctx.current_branch(ctx.cwd) if ctx.current_branch is not None else _current_branch(ctx.cwd)
        targets = [branch] if branch and not flags & {"--all", "--mirror"} else ["*"]
    protected = any(t == "*" or ctx.is_protected_branch(t) for t in targets)
    label = ", ".join(targets)
    if protected and force:
        return BandVerdict(Band.NUCLEAR, f"git push forçado em branch protegida ({label})", "git:push_force_protected", outbound_hosts=())
    if protected:
        return BandVerdict(Band.PRESENCA, f"git push para branch protegida ({label})", "git:push_protected")
    if force:
        return _classified(f"git push forçado ({label})", "git:push_force")
    return _classified(f"git push ({label})", "git:push")


def _current_branch(cwd: Path) -> str | None:
    """Branch atual lendo ``.git/HEAD`` (sem subprocesso); None se não resolve."""
    for base in (cwd, *cwd.parents):
        head = base / ".git"
        if head.is_file():  # worktree: "gitdir: <caminho>"
            try:
                pointer = head.read_text(encoding="utf-8").strip()
            except OSError:
                return None
            if not pointer.startswith("gitdir:"):
                return None
            head = Path(pointer.split(":", 1)[1].strip())
            if not head.is_absolute():
                head = base / head
        if head.is_dir():
            try:
                ref = (head / "HEAD").read_text(encoding="utf-8").strip()
            except OSError:
                return None
            return ref.removeprefix("ref: refs/heads/") if ref.startswith("ref: ") else None
    return None


def _pkg(program: str, args: list[str], ctx: BandContext, piped_in: bool) -> BandVerdict:
    flags, operands = _split_flags(args)
    verb = operands[0] if operands else ""
    words = set(args)
    if program == "dpkg":
        if flags & {"-r", "-P", "--remove", "--purge"}:
            verb = "remove"
        elif flags & {"-l", "-L", "-s", "-S", "--list", "--status"}:
            return _livre("dpkg: consulta", "pkg:read")
    if program == "pacman" and any(a.startswith("-R") for a in args):
        verb = "remove"
    if program == "pacman" and any(re.fullmatch(r"-Q\w*|-S[si]\w*", a) for a in args):
        return _livre("pacman: consulta", "pkg:read")
    if verb in _PKG_READ or (words & _PKG_READ and verb not in _PKG_REMOVE):
        return _livre(f"{program} {verb}: consulta", "pkg:read")
    if "--allow-remove-essential" in args:
        return BandVerdict(Band.NUCLEAR, "remoção de pacote essencial forçada", "pkg:essential")
    if verb in _PKG_REMOVE or verb == "remove":
        packages = [p for p in operands[1:] if not p.startswith("-")] if operands and operands[0] in _PKG_REMOVE | {"remove"} else operands
        if any(_has_glob_or_var(p) or any(ch in p for ch in "*?[") for p in packages):
            return BandVerdict(Band.NUCLEAR, "remoção de pacotes por padrão (pode pegar essenciais)", "pkg:pattern")
        names = {re.split(r"[:=<>]", p, maxsplit=1)[0] for p in packages}
        essential = sorted(n for n in names if n in _ESSENTIAL_PACKAGES or n.startswith(("linux-image", "linux-headers", "grub", "systemd", "libc6")))
        if essential:
            return BandVerdict(Band.NUCLEAR, f"remove pacote essencial: {', '.join(essential)}", "pkg:essential")
        return _classified(f"remove pacote(s): {', '.join(sorted(names)) or '?'}", "pkg:remove")
    if verb in ("autoremove", "autoclean"):
        return BandVerdict(Band.PRESENCA, f"{program} {verb} remove pacotes em lote", "pkg:autoremove")
    return _classified(f"{program} {verb}".strip(), f"pkg:{verb or 'other'}")


def _systemctl(program: str, args: list[str], ctx: BandContext, piped_in: bool) -> BandVerdict:
    flags, operands = _split_flags(args)
    verb = operands[0] if operands else "list-units"
    if verb in ("status", "show", "cat", "is-active", "is-enabled", "is-failed", "list-units", "list-unit-files", "list-timers", "list-dependencies", "list-sockets", "help"):
        return _livre(f"systemctl {verb}: leitura", "systemctl:read")
    user = "--user" in flags
    if verb in ("enable", "disable", "mask", "unmask", "link", "edit", "set-default", "preset", "revert", "daemon-reload"):
        if user:
            return _classified(f"systemctl --user {verb}", "systemctl:user_unit")
        return BandVerdict(Band.PRESENCA, f"systemctl {verb}: unit do sistema", "systemctl:system_unit")
    if verb in ("poweroff", "halt", "kexec"):
        return BandVerdict(Band.NUCLEAR, f"systemctl {verb}", "power:off")
    if verb in ("reboot", "suspend", "hibernate", "isolate", "emergency", "rescue"):
        return BandVerdict(Band.PRESENCA, f"systemctl {verb}", "power")
    return _classified(f"systemctl {verb}", f"systemctl:{verb}")


def _power(program: str, args: list[str], ctx: BandContext, piped_in: bool) -> BandVerdict:
    text = " ".join(args)
    if program in ("poweroff", "halt") or (program == "shutdown" and re.search(r"(-h|-P)\s+now|\bnow\b", text)) or (program == "reboot" and re.search(r"(-f|--force)", text)):
        return BandVerdict(Band.NUCLEAR, f"{program} {text}".strip(), "power:off")
    return BandVerdict(Band.PRESENCA, f"{program} {text}".strip(), "power")


def _docker(program: str, args: list[str], ctx: BandContext, piped_in: bool) -> BandVerdict:
    _flags, operands = _split_flags(args)
    words = operands[:2]
    if words[:1] in (["ps"], ["images"], ["logs"], ["inspect"], ["version"], ["info"], ["stats"], ["top"], ["history"], ["search"]) or words[1:2] in (["ls"], ["inspect"], ["ps"]):
        return _livre(f"docker {' '.join(words)}: leitura", "docker:read")
    if words == ["system", "prune"]:
        return BandVerdict(Band.PRESENCA, "docker system prune", "docker:system_prune")
    if words[:1] == ["volume"] and words[1:2] in (["rm"], ["prune"]):
        return BandVerdict(Band.NUCLEAR, "apaga volume docker (dados sem snapshot)", "docker:volume_rm")
    return _classified(f"docker {' '.join(words)}".strip(), "docker")


_SQL_DESTROY = re.compile(r"\b(drop\s+(table|database|schema|index|view)|truncate|delete\s+from\s+\w+\s*(;|$)|flushall|flushdb|dropdatabase)\b", re.IGNORECASE)


def _db(program: str, args: list[str], ctx: BandContext, piped_in: bool) -> BandVerdict:
    text = " ".join(args)
    if not _SQL_DESTROY.search(text):
        return _classified(f"{program}: cliente de banco", f"db:{program}")
    if program == "sqlite3":
        files = [a for a in args if not a.startswith("-")][:1]
        if files and ctx.resolve(files[0]).exists():
            return _deletion("sqlite3", files, ctx, kind="overwrite")
    host = _db_host(args)
    if host and host not in ("localhost", "127.0.0.1", "::1"):
        return BandVerdict(Band.NUCLEAR, f"DROP/TRUNCATE em banco remoto ({host})", "db:remote_destroy")
    return BandVerdict(Band.PRESENCA, "DROP/TRUNCATE em banco local", "db:local_destroy")


def _db_host(args: list[str]) -> str:
    for i, arg in enumerate(args):
        if arg in ("-h", "--host") and i + 1 < len(args):
            return args[i + 1]
        if arg.startswith("--host="):
            return arg.split("=", 1)[1]
        if arg.startswith("-h") and len(arg) > 2:
            return arg[2:]
        match = re.match(r"\w+://(?:[^@/]+@)?([^:/?]+)", arg)
        if match:
            return match.group(1)
    return ""


def _outbound(program: str, args: list[str], ctx: BandContext, piped_in: bool) -> BandVerdict:
    hosts: list[str] = []
    for arg in args:
        match = re.match(r"(?:[\w.-]+@)?([\w.-]+):", arg)
        if match and not arg.startswith("/"):
            hosts.append(match.group(1).lower())
    if program == "ssh":
        _flags, operands = _split_flags(args)
        if operands:
            hosts.append(operands[0].split("@")[-1].lower())
    if program == "rsync" and not hosts:
        return _mv_cp("cp", [a for a in args if not a.startswith("-")], ctx, piped_in)
    return BandVerdict(Band.CLASSIFICADA, f"{program}: envia dados para fora", "outbound:" + program, outbound_hosts=tuple(dict.fromkeys(hosts)) or ("?",))


def _curl(program: str, args: list[str], ctx: BandContext, piped_in: bool) -> BandVerdict:
    urls = [a for a in args if re.match(r"\w+://", a)]
    hosts = tuple(dict.fromkeys(_host(u) for u in urls if _host(u)))
    sends = any(
        a in ("-d", "--data", "--data-raw", "--data-binary", "--data-urlencode", "-F", "--form", "-T", "--upload-file", "--post-data", "--post-file", "--body-data", "--body-file", "--json")
        or a.startswith(("--data", "--post-", "--json"))
        for a in args
    )
    method = next((args[i + 1].upper() for i, a in enumerate(args) if a in ("-X", "--request", "--method") and i + 1 < len(args)), "")
    sends = sends or method in ("POST", "PUT", "PATCH", "DELETE") or any("?" in u for u in urls)
    writes = any(a in ("-o", "--output", "-O", "--remote-name", "-P", "--directory-prefix") for a in args) or program == "wget"
    if sends:
        return BandVerdict(Band.CLASSIFICADA, f"{program} envia dados", f"outbound:{program}", outbound_hosts=hosts or ("?",), mutates=writes)
    return BandVerdict(Band.CLASSIFICADA, f"{program} baixa conteúdo", f"download:{program}", outbound_hosts=(), mutates=writes)


def _crontab(program: str, args: list[str], ctx: BandContext, piped_in: bool) -> BandVerdict:
    if args[:1] == ["-l"]:
        return _livre("crontab -l", "crontab:read")
    return BandVerdict(Band.PRESENCA, "agenda trabalho sem humano (crontab/at)", "schedule:crontab")


def _gpg(program: str, args: list[str], ctx: BandContext, piped_in: bool) -> BandVerdict:
    if any(a.startswith("--delete") for a in args):
        return BandVerdict(Band.NUCLEAR, "apaga chaves GPG", "keys:gpg_delete")
    return _classified("gpg", "gpg")


def _interpreter_verdict(program: str, args: list[str]) -> BandVerdict:
    if program.startswith("python") and len(args) >= 2 and args[0] == "-m":
        module = args[1]
        if module in ("pytest", "mypy", "pyright"):
            return _livre(f"python -m {module}", f"read:{module}")
        if module == "orion.install":
            return BandVerdict(Band.NUCLEAR, "troca o código instalado do ORION (ADR-044)", "orion_update")
        if module == "pip" and args[2:3] in (["list"], ["show"], ["freeze"], ["check"]):
            return _livre("pip: consulta", "read:pip")
    if args[:1] in (["--version"], ["-V"]):
        return _livre(f"{program} --version", "read:version")
    return _classified(f"{program}: código arbitrário", f"interpreter:{program}")


def _generic_verdict(program: str, args: list[str], ctx: BandContext) -> BandVerdict:
    if program in ("ruff", "black", "isort", "eslint", "prettier"):
        checking = "--check" in args or "--diff" in args or (program == "ruff" and args[:1] == ["check"] and "--fix" not in args)
        if program == "eslint" and "--fix" not in args:
            checking = True
        if program == "prettier" and "--write" not in args and "-w" not in args:
            checking = True
        if checking:
            return _livre(f"{program}: leitura", f"read:{program}")
        return _livre(f"{program} formata arquivos no escopo", f"{program}:write", mutates=True)
    if program in ("mkdir", "touch", "ln"):
        _flags, operands = _split_flags(args)
        worst, blocked, rule = Band.LIVRE, False, f"{program}:scope"
        for op in operands:
            if _has_glob_or_var(op):
                return _classified(f"{program} com alvo opaco", f"{program}:opaque", unresolved=True)
            band, is_blocked, zone_rule = _band_for_zone(ctx.zone(op))
            blocked = blocked or is_blocked
            if band > worst:
                worst, rule = band, f"{program}:{zone_rule}"
        return BandVerdict(worst, f"{program} ({rule})", rule, blocked=blocked, mutates=True)
    if program in ("chmod", "chown", "chgrp"):
        _flags, operands = _split_flags(args)
        targets = operands[1:]
        worst = Band.CLASSIFICADA
        rule = f"{program}"
        blocked = False
        for op in targets:
            if _has_glob_or_var(op):
                continue
            band, is_blocked, zone_rule = _band_for_zone(ctx.zone(op))
            blocked = blocked or is_blocked
            if band > worst:
                worst, rule = band, f"{program}:{zone_rule}"
        return BandVerdict(worst, f"{program} muda permissões", rule, blocked=blocked)
    if program == "cp":
        return _mv_cp(program, args, ctx, False)
    if program in ("curl", "wget"):
        return _curl(program, args, ctx, False)
    if program == "rsync":
        return _outbound(program, args, ctx, False)
    if program in ("env", "printenv", "export"):
        if program == "env" and args:
            return _program_verdict(args, ctx, piped_in=False)
        return _classified(f"{program} pode expor variáveis com segredo", f"env:{program}")
    if program == "awk" or program == "gawk":
        script = " ".join(args)
        if not re.search(r"system\s*\(|\|\s*\"|>\s*\"|print\s*>|getline", script):
            return _livre("awk: leitura", "read:awk")
    return _classified(f"{program}", f"generic:{program}")


_HANDLERS: dict[str, Callable[[str, list[str], BandContext, bool], BandVerdict]] = {
    "rm": _rm,
    "unlink": _rm,
    "rmdir": _rmdir,
    "mv": _mv_cp,
    "cp": _mv_cp,
    "sed": _sed,
    "perl": _sed,
    "truncate": _truncate,
    "dd": _dd,
    "find": _find,
    "git": _git,
    "systemctl": _systemctl,
    "shutdown": _power,
    "reboot": _power,
    "poweroff": _power,
    "halt": _power,
    "docker": _docker,
    "psql": _db,
    "mysql": _db,
    "mariadb": _db,
    "sqlite3": _db,
    "mongosh": _db,
    "mongo": _db,
    "redis-cli": _db,
    "crontab": _crontab,
    "at": _crontab,
    "gpg": _gpg,
    "gpg2": _gpg,
    **{name: _pkg for name in _PKG_MANAGERS},
    **{name: _outbound for name in _OUTBOUND_PROGRAMS if name != "rsync"},
}
