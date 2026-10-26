"""
O.R.I.O.N TUI (Terminal User Interface) Module.

Design System Oficial Deep Cosmos & Glacial Platinum, Banner Adaptativo,
Barra de Status, Autocomplete Flutuante (/ e @) e Prompt Interativo prompt_toolkit.
"""

from __future__ import annotations

from orion.tui.banner import BannerRenderer
from orion.tui.completer import (
    OFFICIAL_SLASH_COMMANDS,
    GitIgnoreMatcher,
    OrionCompleter,
    PathMentionCompleter,
    SlashCommandCompleter,
    SlashCommandInfo,
    parse_mentions,
    resolve_mentions,
)
from orion.tui.console import get_console, reset_console
from orion.tui.keybindings import create_key_bindings
from orion.tui.prompt import InteractivePrompt, get_prompt_style
from orion.tui.status_bar import ReasoningEffort, SessionStatusBar
from orion.tui.theme import ORION_COLORS, get_orion_theme

__all__ = [
    "ORION_COLORS",
    "get_orion_theme",
    "get_console",
    "reset_console",
    "BannerRenderer",
    "ReasoningEffort",
    "SessionStatusBar",
    "SlashCommandInfo",
    "OFFICIAL_SLASH_COMMANDS",
    "GitIgnoreMatcher",
    "SlashCommandCompleter",
    "PathMentionCompleter",
    "OrionCompleter",
    "parse_mentions",
    "resolve_mentions",
    "create_key_bindings",
    "InteractivePrompt",
    "get_prompt_style",
]
