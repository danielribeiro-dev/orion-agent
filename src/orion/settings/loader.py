"""Carregamento e merge de settings em camadas: user < projeto < local."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from orion.settings.io import read_json_object, write_private_json
from orion.settings.models import (
    AgentsSettings,
    HookSpec,
    ModelsSettings,
    Permissions,
    Settings,
)
from orion.settings.trust import ProjectTrust, digest_of

_M = TypeVar("_M", bound=BaseModel)

logger = logging.getLogger(__name__)

SETTINGS_NAME = "settings.json"
LOCAL_SETTINGS_NAME = "settings.local.json"
LEGACY_CONFIG_NAME = "config.json"
_LEGACY_KEYS = ("model", "effort", "mode", "daily_budget_usd")


@dataclass(frozen=True)
class LoadedSettings:
    """Resultado do carregamento."""

    effective: Settings
    user: Settings
    project: Settings
    local: Settings
    #: Existe settings de projeto com conteúdo de risco ainda sem confiança.
    project_needs_trust: bool = False
    project_digest: str | None = None
    notices: list[str] = field(default_factory=list)

    def project_summary(self) -> list[str]:
        """Linhas legíveis do que o projeto pede para executar ou liberar."""
        lines: list[str] = []
        for event, specs in self.project.hooks.items():
            lines.extend(f"hook {event}: {spec.command}" for spec in specs)
        lines.extend(f"allow: {rule}" for rule in self.project.permissions.allow)
        if self.project.mode:
            lines.append(f"mode: {self.project.mode}")
        lines.extend(f"mcp: {name}" for name in self.project.mcp)
        if self.project.env:
            lines.append("env: " + ", ".join(sorted(self.project.env)))
        if self.project.daily_budget_usd is not None:
            lines.append(f"daily_budget_usd: {self.project.daily_budget_usd}")
        return lines


def user_settings_path(home: Path) -> Path:
    return home / SETTINGS_NAME


def project_settings_path(workspace: Path) -> Path:
    return workspace / ".orion" / SETTINGS_NAME


def local_settings_path(workspace: Path) -> Path:
    return workspace / ".orion" / LOCAL_SETTINGS_NAME


def _parse(data: dict[str, Any] | None, origin: str, notices: list[str]) -> Settings:
    if not data:
        return Settings()
    try:
        return Settings.model_validate(data)
    except ValidationError as exc:
        notices.append(f"settings inválido ignorado ({origin}): {exc.error_count()} erro(s)")
        logger.warning("settings inválido em %s: %s", origin, exc)
        return Settings()


def _dedupe(*groups: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for group in groups:
        for item in group:
            seen.setdefault(item, None)
    return list(seen)


def merge(layers: list[Settings]) -> Settings:
    """Combina camadas da menor para a maior precedência.

    Escalares da camada mais alta sobrescrevem; listas de permissões e hooks
    concatenam (sem duplicar); ``mcp`` e ``env`` mesclam por chave.
    """
    result = Settings()
    for layer in layers:
        hooks: dict[str, list[HookSpec]] = {k: list(v) for k, v in result.hooks.items()}
        for event, specs in layer.hooks.items():
            bucket = hooks.setdefault(event, [])
            bucket.extend(s for s in specs if s not in bucket)
        result = Settings(
            model=layer.model or result.model,
            effort=layer.effort or result.effort,
            mode=layer.mode or result.mode,
            daily_budget_usd=(
                layer.daily_budget_usd
                if layer.daily_budget_usd is not None
                else result.daily_budget_usd
            ),
            permissions=Permissions(
                allow=_dedupe(result.permissions.allow, layer.permissions.allow),
                deny=_dedupe(result.permissions.deny, layer.permissions.deny),
                ask=_dedupe(result.permissions.ask, layer.permissions.ask),
            ),
            hooks=hooks,
            mcp={**result.mcp, **layer.mcp},
            env={**result.env, **layer.env},
            agents=_merge_agents(result.agents, layer.agents),
            models=ModelsSettings(
                tiers={**result.models.tiers, **layer.models.tiers},
                profiles={**result.models.profiles, **layer.models.profiles},
            ),
            daemon=layer.daemon if "daemon" in layer.model_fields_set else result.daemon,
            ui=_merge_model(result.ui, layer.ui),
        )
    return result


def _merge_model(base: _M, top: _M) -> _M:
    """Campos explicitamente definidos na camada mais alta sobrescrevem os de baixo."""
    return base.model_copy(update={k: getattr(top, k) for k in top.model_fields_set})


def _merge_agents(base: AgentsSettings, top: AgentsSettings) -> AgentsSettings:
    """Escalares da camada mais alta sobrescrevem; campos não definidos herdam."""
    merged = base.model_dump()
    merged.update({k: v for k, v in top.model_dump().items() if v is not None})
    return AgentsSettings(**merged)


def _read_user_layer(home: Path, notices: list[str]) -> Settings:
    data = read_json_object(user_settings_path(home))
    if data is None:
        legacy = read_json_object(home / LEGACY_CONFIG_NAME)
        if legacy:
            data = {k: legacy[k] for k in _LEGACY_KEYS if k in legacy}
    return _parse(data, "user", notices)


def load_settings(
    home: Path,
    workspace: Path | None = None,
    *,
    trust: ProjectTrust | None = None,
    extra_layers: Sequence[Settings] = (),
) -> LoadedSettings:
    """Carrega as camadas aplicando a política de confiança do projeto.

    ``extra_layers`` (plugins instalados pelo Senhor) entram entre user e projeto.
    """
    notices: list[str] = []
    user = _read_user_layer(home, notices)
    project = Settings()
    local = Settings()
    needs_trust = False
    digest: str | None = None
    effective_project = Settings()

    if workspace is not None:
        path = project_settings_path(workspace)
        try:
            raw = path.read_bytes()
        except OSError:
            raw = None
        if raw is not None:
            digest = digest_of(raw)
            project = _parse(read_json_object(path), "projeto", notices)
            registry = trust if trust is not None else ProjectTrust(home)
            if not project.has_risky_content() or registry.is_trusted(workspace, digest):
                effective_project = project
            else:
                needs_trust = True
                effective_project = project.restricted()
        local = _parse(read_json_object(local_settings_path(workspace)), "local", notices)

    # O daemon é da máquina, não do projeto (ADR-032): só a camada do usuário o configura.
    project_layers = [_drop(layer, {"daemon"}) for layer in (*extra_layers, effective_project, local)]
    return LoadedSettings(
        effective=merge([user, *project_layers]),
        user=user,
        project=project,
        local=local,
        project_needs_trust=needs_trust,
        project_digest=digest,
        notices=notices,
    )


def _drop(layer: Settings, fields: set[str]) -> Settings:
    """Remove campos de uma camada (voltam ao padrão e deixam de contar como definidos)."""
    if not fields & layer.model_fields_set:
        return layer
    return Settings(**layer.model_dump(include=layer.model_fields_set - fields))


def _update_layer(path: Path, updates: dict[str, Any]) -> None:
    current = read_json_object(path) or {}
    current.update({k: v for k, v in updates.items() if v is not None})
    write_private_json(path, current)


def save_user_settings(home: Path, updates: dict[str, Any]) -> None:
    """Mescla ``updates`` em ``~/.orion/settings.json`` (0600, atômico)."""
    path = user_settings_path(home)
    if read_json_object(path) is None:
        legacy = read_json_object(home / LEGACY_CONFIG_NAME) or {}
        seed = {k: legacy[k] for k in _LEGACY_KEYS if k in legacy}
        if seed:
            write_private_json(path, seed)
    _update_layer(path, updates)


def append_local_rule(workspace: Path, effect: str, rule: str) -> None:
    """Acrescenta uma regra de permissão à camada local (fora do git)."""
    path = local_settings_path(workspace)
    data = read_json_object(path) or {}
    perms = data.get("permissions")
    perms = perms if isinstance(perms, dict) else {}
    rules = perms.get(effect)
    rules = rules if isinstance(rules, list) else []
    if rule not in rules:
        rules.append(rule)
    perms[effect] = rules
    data["permissions"] = perms
    write_private_json(path, data)
