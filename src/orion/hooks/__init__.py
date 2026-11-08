"""Hooks do ORION (scripts em pontos fixos do ciclo do agente)."""

from orion.hooks.runner import (
    BLOCK_EXIT_CODE,
    HookOutcome,
    HookRunner,
    sanitize_hook_text,
)

__all__ = ["BLOCK_EXIT_CODE", "HookOutcome", "HookRunner", "sanitize_hook_text"]
