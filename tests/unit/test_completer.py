"""
Unit tests for OrionCompleter, SlashCommandCompleter, PathMentionCompleter,
and mention parsing/resolution.
"""

import tempfile
from pathlib import Path

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

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


class TestSlashCommandCompleter:
    """Testes do completer de comandos slash (/)."""

    def test_slash_co_suggests_compact_context_and_cost(self) -> None:
        """Cenário de Teste Obrigatório 1: Digitar /co sugere /compact, /context e /cost."""
        completer = SlashCommandCompleter()
        doc = Document("/co")
        completions = list(completer.get_completions(doc, CompleteEvent()))

        texts = [c.text for c in completions]
        assert "/compact" in texts
        assert "/context" in texts
        assert "/cost" in texts

        # Validar que possuem descrições associadas
        compact_comp = next(c for c in completions if c.text == "/compact")
        assert compact_comp.display_meta
        assert "compactar" in str(compact_comp.display_meta).lower()

        context_comp = next(c for c in completions if c.text == "/context")
        assert context_comp.display_meta
        assert "contexto" in str(context_comp.display_meta).lower() or "tokens" in str(context_comp.display_meta).lower()

        cost_comp = next(c for c in completions if c.text == "/cost")
        assert cost_comp.display_meta
        assert "custo" in str(cost_comp.display_meta).lower()

    def test_slash_command_info_repr(self) -> None:
        cmd = SlashCommandInfo("custom", "Custom description", icon="✨", category="test")
        assert cmd.name == "/custom"
        assert repr(cmd) == "<SlashCommandInfo /custom: Custom description>"

    def test_slash_root_lists_all_commands(self) -> None:
        """Digitar apenas / sugere todos os comandos cadastrados."""
        completer = SlashCommandCompleter()
        doc = Document("/")
        completions = list(completer.get_completions(doc, CompleteEvent()))

        assert len(completions) >= len(OFFICIAL_SLASH_COMMANDS)
        texts = [c.text for c in completions]
        assert "/plan" in texts
        assert "/goal" in texts
        assert "/grill-me" in texts
        assert "/doctor" in texts
        assert "/mcp" in texts

    def test_slash_fuzzy_matching(self) -> None:
        """Busca fuzzy ao digitar /cpt deve sugerir /compact."""
        completer = SlashCommandCompleter()
        doc = Document("/cpt")
        completions = list(completer.get_completions(doc, CompleteEvent()))

        texts = [c.text for c in completions]
        assert "/compact" in texts

    def test_slash_case_insensitivity(self) -> None:
        """Busca deve ser insensível a maiúsculas e minúsculas (/CO)."""
        completer = SlashCommandCompleter()
        doc = Document("/CO")
        completions = list(completer.get_completions(doc, CompleteEvent()))

        texts = [c.text for c in completions]
        assert "/compact" in texts
        assert "/context" in texts

    def test_non_slash_does_not_suggest(self) -> None:
        """Texto que não começa com / não deve acionar SlashCommandCompleter."""
        completer = SlashCommandCompleter()
        doc = Document("co")
        completions = list(completer.get_completions(doc, CompleteEvent()))
        assert len(completions) == 0

        doc_space = Document("/plan some arg")
        completions_space = list(completer.get_completions(doc_space, CompleteEvent()))
        assert len(completions_space) == 0


class TestGitIgnoreMatcher:
    """Testes da filtragem por regras de .gitignore e pastas padrão."""

    def test_default_ignored_directories(self) -> None:
        matcher = GitIgnoreMatcher()
        assert matcher.is_ignored(".git", is_dir=True)
        assert matcher.is_ignored(".venv", is_dir=True)
        assert matcher.is_ignored("node_modules", is_dir=True)
        assert matcher.is_ignored("__pycache__", is_dir=True)
        assert matcher.is_ignored(".pytest_cache", is_dir=True)

    def test_default_ignored_files(self) -> None:
        matcher = GitIgnoreMatcher()
        assert matcher.is_ignored("test.pyc")
        assert matcher.is_ignored("binary.so")
        assert matcher.is_ignored(".DS_Store")

    def test_custom_gitignore_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            gitignore_file = tmp_path / ".gitignore"
            gitignore_file.write_text("*.secret\nignored_folder/\n/anchored_file.txt\nsub/*\n# Comment\n\nbuild_out")

            matcher = GitIgnoreMatcher(workspace_root=tmp_path)
            assert matcher.is_ignored("key.secret")
            assert matcher.is_ignored("ignored_folder", is_dir=True)
            assert matcher.is_ignored("anchored_file.txt")
            assert matcher.is_ignored("sub/temp.txt")
            assert matcher.is_ignored("build_out")
            assert not matcher.is_ignored("main.py")

    def test_gitignore_unreadable_file_handles_gracefully(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            # Diretório nomeado .gitignore para simular erro de leitura
            (tmp_path / ".gitignore").mkdir()
            matcher = GitIgnoreMatcher(workspace_root=tmp_path)
            assert matcher.is_ignored(".git", is_dir=True)


class TestPathMentionCompleter:
    """Testes do completer de caminhos (@)."""

    def test_suggests_src_subdirectories_and_files(self) -> None:
        """Cenário de Teste Obrigatório 2: Digitar @src/ sugere subdiretórios/arquivos em src/ sem .git ou node_modules."""
        repo_root = Path(__file__).resolve().parents[2]
        completer = PathMentionCompleter(workspace_root=repo_root)

        doc = Document("@src/")
        completions = list(completer.get_completions(doc, CompleteEvent()))

        texts = [c.text for c in completions]
        assert any("src/orion" in t for t in texts)

        # Garantir que jamais liste .git ou node_modules
        assert not any(".git" in t for t in texts)
        assert not any("node_modules" in t for t in texts)
        assert not any("__pycache__" in t for t in texts)

    def test_suggests_top_level_files_on_at_symbol(self) -> None:
        """Digitar apenas @ sugere os arquivos e pastas da raiz do projeto."""
        repo_root = Path(__file__).resolve().parents[2]
        completer = PathMentionCompleter(workspace_root=repo_root)

        doc = Document("@")
        completions = list(completer.get_completions(doc, CompleteEvent()))

        texts = [c.text for c in completions]
        assert "src/" in texts
        assert "docs/" in texts
        assert "README.md" in texts
        assert "pyproject.toml" in texts

        # Pastas e arquivos ignorados não devem aparecer
        assert ".git/" not in texts
        assert ".venv/" not in texts

    def test_suggests_with_prefix(self) -> None:
        """Digitar @s sugere arquivos ou diretórios começando com s (ex: src/)."""
        repo_root = Path(__file__).resolve().parents[2]
        completer = PathMentionCompleter(workspace_root=repo_root)

        doc = Document("@s")
        completions = list(completer.get_completions(doc, CompleteEvent()))

        texts = [c.text for c in completions]
        assert "src/" in texts

    def test_mock_workspace_directory_structure(self) -> None:
        """Testa o completer em uma árvore temporária com arquivos e pastas aninhadas."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "src").mkdir()
            (root / "src" / "agent.py").write_text("code")
            (root / "src" / "utils").mkdir()
            (root / "node_modules").mkdir()
            (root / ".git").mkdir()
            (root / "README.md").write_text("readme")

            completer = PathMentionCompleter(workspace_root=root)

            doc = Document("@src/")
            completions = list(completer.get_completions(doc, CompleteEvent()))

            texts = [c.text for c in completions]
            assert "src/utils/" in texts
            assert "src/agent.py" in texts
            assert not any("node_modules" in t for t in texts)
            assert not any(".git" in t for t in texts)

    def test_nonexistent_directory_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            completer = PathMentionCompleter(workspace_root=tmp_dir)
            doc = Document("@nonexistent/sub/")
            completions = list(completer.get_completions(doc, CompleteEvent()))
            assert len(completions) == 0


class TestOrionCompleter:
    """Testes da alternância de contexto no OrionCompleter."""

    def test_orion_completer_slash_dispatch(self) -> None:
        completer = OrionCompleter()
        doc = Document("/co")
        completions = list(completer.get_completions(doc, CompleteEvent()))
        texts = [c.text for c in completions]
        assert "/compact" in texts

    def test_orion_completer_at_dispatch(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        completer = OrionCompleter(workspace_root=repo_root)
        doc = Document("@src/")
        completions = list(completer.get_completions(doc, CompleteEvent()))
        texts = [c.text for c in completions]
        assert any("src/orion" in t for t in texts)

    def test_orion_completer_regular_text_no_completions(self) -> None:
        completer = OrionCompleter()
        doc = Document("What is the meaning of life?")
        completions = list(completer.get_completions(doc, CompleteEvent()))
        assert len(completions) == 0


class TestMentionParserAndResolver:
    """Testes de parse_mentions e resolve_mentions."""

    def test_parse_mentions_extracts_paths(self) -> None:
        text = "Please examine @src/orion/cli.py, @README.md and also (@tests/conftest.py)!"
        mentions = parse_mentions(text)
        assert "src/orion/cli.py" in mentions
        assert "README.md" in mentions
        assert "tests/conftest.py" in mentions

    def test_resolve_mentions_resolves_valid_files(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        text = "Check @src/orion/cli.py and @pyproject.toml"
        resolved = resolve_mentions(text, workspace_root=repo_root)

        assert "src/orion/cli.py" in resolved
        assert "pyproject.toml" in resolved
        assert resolved["src/orion/cli.py"].is_file()
        assert resolved["pyproject.toml"].is_file()

    def test_resolve_mentions_rejects_directory_traversal(self) -> None:
        """Garante que @../../etc/passwd seja rejeitado por escapar a raiz do workspace."""
        repo_root = Path(__file__).resolve().parents[2]
        text = "Malicious mention @../../../../etc/passwd"
        resolved = resolve_mentions(text, workspace_root=repo_root)
        assert len(resolved) == 0
