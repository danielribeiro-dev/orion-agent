"""
O.R.I.O.N Memory Subsystem — Cognitive Continuity (v0.2.0)

The Triple Memory Architecture:
  - Layer 1 (Lexical/Episodic): SQLite WAL + FTS5 BM25 (TimelineManager)
  - Layer 2 (Semantic): FastEmbed ONNX local (VectorStore)
  - Layer 3 (Structured): Typed facts with anti-poisoning state machine (FactsStore)
"""
