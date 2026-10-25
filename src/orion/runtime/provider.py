"""
O.R.I.O.N — Runtime Provider Contract
Abstract base class and result type for all runtime backends.

A RuntimeProvider receives a dispatched Action and returns a RuntimeResult.
The LocalRuntimeProvider (Sprint 3) is the first concrete implementation.
Future providers may wrap sandboxed environments, Docker containers, or remote
execution APIs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RuntimeResult:
    """Immutable result returned by a RuntimeProvider after executing a tool.

    Attributes:
        success     : True if the tool completed without error.
        output      : String output produced by the tool (stdout, file content…).
        error       : Error message if success is False; empty string otherwise.
        metadata    : Optional structured metadata (e.g. exit_code, line_count).
    """

    success: bool
    output: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, output: str, **metadata: Any) -> "RuntimeResult":
        """Convenience constructor for a successful result."""
        return cls(success=True, output=output, metadata=metadata)

    @classmethod
    def fail(cls, error: str, **metadata: Any) -> "RuntimeResult":
        """Convenience constructor for a failed result."""
        return cls(success=False, output="", error=error, metadata=metadata)


class BaseRuntimeProvider(ABC):
    """Abstract contract for all runtime backends.

    Every provider must implement `execute`, which receives the tool name and
    its parameters and returns a RuntimeResult.
    """

    @abstractmethod
    async def execute(self, tool: str, params: dict[str, Any]) -> RuntimeResult:
        """Execute *tool* with *params* and return a RuntimeResult.

        Args:
            tool   : Canonical tool name (e.g. "read_file", "run_command").
            params : Tool-specific keyword arguments.

        Returns:
            A RuntimeResult with success/failure, output, and optional metadata.
        """
        ...

    @abstractmethod
    def supports(self, tool: str) -> bool:
        """Return True if this provider knows how to handle *tool*."""
        ...
