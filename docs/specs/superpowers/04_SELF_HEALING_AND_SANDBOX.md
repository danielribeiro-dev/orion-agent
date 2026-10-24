# Superpoder 04 — Cérebro de Código, Self-Healing & Sandbox Bubblewrap

> Especificação de análise de código via Tree-sitter, autocura de falhas de execução e isolamento seguro de plugins.

---

## 1. O Salto da Engenharia de Código: Tree-sitter e AST-Grep

Na abordagem legada, a validação de código dependia do `ast.parse` nativo do Python, incapaz de tratar outras linguagens e gerando diffs quebrados.

Em 2026, a engenharia de ponta adota:
- **Tree-sitter Multi-Linguagem:** Análise de árvore sintática abstrata para Python, TypeScript, Rust, Go, C++ e SQL.
- **Diff Match Patch Cirúrgico:** Edição de blocos de código com correspondência exata, sem risco de truncar arquivos longos.

---

## 2. O Ciclo de Auto-Cura (Self-Healing)

```
[Comando ou Teste Falha] ── (stderr com Traceback)
                 │
                 ▼
[Error Classifier (Local Reasoning Model / Qwen Coder)]
  • Classificação: RECOVERABLE | USER_ACTION_NEEDED | FATAL
                 │
        ┌────────┴────────┐
        ▼                 ▼
[RECOVERABLE]      [USER_ACTION_NEEDED]
• Erro de alias    • Permissão negada / sudo
• Dep ausente      • Conflito de merge
• Porta ocupada    • Bug de lógica complexo
        │                 │
  (Auto-fix silencioso    (Apresenta diagnóstico claro
   limite máx 2 retries)   e proposta de correção)
```

---

## 3. Sandbox Efêmero com Bubblewrap (`bwrap`)

Quando o ORION cria ou testa novos scripts e plugins:
- O processo é enjaulado via **Bubblewrap** (o mesmo motor de segurança do Flatpak).
- O container efêmero é montado em 2ms com acesso somente-leitura à raiz do sistema e bloqueio total da pasta `~/.ssh` e `~/.gnupg`.
- Limites estritos de tempo (30s) e memória (512MB) impedem loops infinitos ou exaustão de hardware.
