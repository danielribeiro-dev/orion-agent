"""Confiança na primeira vez para settings de projeto (trust-on-first-use).

A decisão fica em ``~/.orion/trusted_projects.json`` (0600) como
``{caminho_do_workspace: sha256_do_settings.json}``. Se o arquivo do projeto
mudar, o hash deixa de casar e a confiança é pedida de novo.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from orion.settings.io import read_json_object, write_private_json

TRUST_FILE = "trusted_projects.json"


def digest_of(raw: bytes) -> str:
    """Hash estável do conteúdo bruto do settings do projeto."""
    return hashlib.sha256(raw).hexdigest()


class ProjectTrust:
    """Registro persistente de projetos confiáveis."""

    def __init__(self, home: Path) -> None:
        self._path = home / TRUST_FILE

    def _load(self) -> dict[str, str]:
        data = read_json_object(self._path) or {}
        return {str(k): str(v) for k, v in data.items() if isinstance(v, str)}

    @staticmethod
    def _key(workspace: Path) -> str:
        return str(workspace.resolve())

    def is_trusted(self, workspace: Path, digest: str) -> bool:
        return self._load().get(self._key(workspace)) == digest

    def trust(self, workspace: Path, digest: str) -> None:
        data = self._load()
        data[self._key(workspace)] = digest
        write_private_json(self._path, data)

    def revoke(self, workspace: Path) -> None:
        data = self._load()
        if data.pop(self._key(workspace), None) is not None:
            write_private_json(self._path, data)
