"""
O.R.I.O.N — Model Gateway Package
Agnóstico de provedor: OpenRouter (primário), Ollama local (failover).
"""

from orion.gateway.models import (
    LLMMessage,
    LLMRequest,
    LLMResponseChunk,
    LLMResponse,
    ModelSpec,
    TokenUsage,
)
from orion.gateway.registry import ModelRegistry
from orion.gateway.providers.base import BaseLLMProvider

__all__ = [
    "LLMMessage",
    "LLMRequest",
    "LLMResponseChunk",
    "LLMResponse",
    "ModelSpec",
    "TokenUsage",
    "ModelRegistry",
    "BaseLLMProvider",
]
