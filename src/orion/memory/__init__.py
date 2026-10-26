"""
O.R.I.O.N Memory Subsystem — Cognitive Continuity (v0.2.0)

The Triple Memory Architecture:
  - Layer 1 (Lexical/Episodic): SQLite WAL + FTS5 BM25 (TimelineManager)
  - Layer 2 (Semantic): FastEmbed ONNX local (VectorStore)
  - Layer 3 (Structured): Typed facts with anti-poisoning state machine (FactsStore)

Sprint 3 additions:
  - FactsStore      — Relational SQLite facts with anti-poisoning state machine
  - CognitiveManifestGenerator — Ultra-compact System Prompt injection (< 250 tokens)
  - MemoryFileSyncer — Bidirectional sync with .orion/memory/MEMORY.md (≤ 200 lines)
  - TelegramHITLConnector — Out-of-band PEP approval via Telegram Bot
  - Cognitive Tools — memorize, recall, deprecate_fact, inspect_environment
"""

from orion.memory.facts_store import FactPoisoningAttempt, FactsStore
from orion.memory.file_syncer import MemoryFileSyncer
from orion.memory.manifest import CognitiveManifestGenerator
from orion.memory.models import (
    CognitiveManifest,
    EnvironmentTelemetry,
    FactCategory,
    FactEntry,
    FactStatus,
    SystemIdentity,
    ToolMasteryLevel,
    UserProfile,
)
from orion.memory.tools import (
    DeprecateFactTool,
    InspectEnvironmentTool,
    MemorizeTool,
    RecallTool,
)

__all__ = [
    # Facts store
    "FactsStore",
    "FactPoisoningAttempt",
    # Models
    "FactEntry",
    "FactStatus",
    "FactCategory",
    "UserProfile",
    "ToolMasteryLevel",
    "SystemIdentity",
    "EnvironmentTelemetry",
    "CognitiveManifest",
    # Manifest
    "CognitiveManifestGenerator",
    # File syncer
    "MemoryFileSyncer",
    # Tools
    "MemorizeTool",
    "RecallTool",
    "DeprecateFactTool",
    "InspectEnvironmentTool",
]
