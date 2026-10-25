"""
O.R.I.O.N — Primitive Tool: base
Abstract base for the 5 native primitive tools.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from orion.runtime.provider import RuntimeResult


class BaseTool(ABC):
    """Base class for the 5 native ORION primitive tools."""

    #: Canonical name used to dispatch from LocalRuntimeProvider
    name: str = ""

    @abstractmethod
    async def run(self, **params: Any) -> RuntimeResult:
        """Execute the tool with the given keyword parameters."""
        ...
