"""
O.R.I.O.N — Primitive Tool: base
Abstract base for native tools, with a JSON-schema contract (ADR-021).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from orion.runtime.provider import RuntimeResult


class BaseTool(ABC):
    """Base class for native ORION tools.

    ``description`` and ``input_schema`` are what the model sees; ``input_schema``
    is also validated against before any execution. ``read_only`` is documentation
    only: the authoritative risk of a tool lives in ``governance/permissions.py``.
    """

    #: Canonical name used to dispatch from LocalRuntimeProvider
    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    input_schema: ClassVar[dict[str, Any]] = {"type": "object", "properties": {}}
    read_only: ClassVar[bool] = False

    @abstractmethod
    async def run(self, **params: Any) -> RuntimeResult:
        """Execute the tool with the given keyword parameters."""
        ...
