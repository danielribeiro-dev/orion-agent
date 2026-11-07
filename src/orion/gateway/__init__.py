"""
O.R.I.O.N — Model Gateway Package
Agnóstico de provedor: OpenRouter (primário), Ollama local (failover).
"""

from orion.gateway.models import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMResponseChunk,
    ModelSpec,
    TokenUsage,
)
from orion.gateway.providers.base import BaseLLMProvider
from orion.gateway.registry import ModelRegistry

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
