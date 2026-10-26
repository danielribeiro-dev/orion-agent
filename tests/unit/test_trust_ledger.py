"""
Tests for CommandTrustLedger (v0.3.0 Sprint 4)

Covers:
  - lookup() — known vs unknown commands
  - record_success() — creates and updates signatures
  - CommandCanonicalizer — canonical pattern derivation and hashing
  - revoke() — removal of trusted commands
  - list_trusted() — listing all entries
  - clear() — full ledger reset
  - Thread-safety (basic)
  - Security: nuclear commands must never be auto-trusted by external code
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from orion.governance.trust_ledger import (
    CommandCanonicalizer,
    CommandSignature,
    CommandTrustLedger,
    TrustLookupResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ledger(tmp_path: Path) -> CommandTrustLedger:
    """In-memory ledger backed by a temp file."""
    return CommandTrustLedger(db_path=tmp_path / "test_trust.db")


# ---------------------------------------------------------------------------
# CommandCanonicalizer
# ---------------------------------------------------------------------------


class TestCommandCanonicalizer:
    def test_git_status_unchanged(self):
        assert CommandCanonicalizer.canonicalize("git status") == "git status"

    def test_git_commit_strips_message(self):
        canonical = CommandCanonicalizer.canonicalize('git commit -m "feat: add X"')
        assert canonical == "git commit -m"

    def test_pytest_strips_path_argument(self):
        canonical = CommandCanonicalizer.canonicalize("pytest tests/unit/test_foo.py")
        assert canonical == "pytest"

    def test_npm_test_unchanged(self):
        assert CommandCanonicalizer.canonicalize("npm test") == "npm test"

    def test_sudo_apt_install_strips_package(self):
        canonical = CommandCanonicalizer.canonicalize("sudo apt install htop")
        assert canonical == "sudo apt install"

    def test_cat_file_strips_path(self):
        canonical = CommandCanonicalizer.canonicalize("cat /tmp/file.txt")
        assert canonical == "cat"

    def test_empty_command_returns_empty(self):
        canonical = CommandCanonicalizer.canonicalize("")
        assert canonical == ""

    def test_canonical_is_lowercase(self):
        canonical = CommandCanonicalizer.canonicalize("Git Status")
        assert canonical == canonical.lower()

    def test_same_pattern_same_hash(self):
        h1 = CommandCanonicalizer.compute_hash("git commit -m")
        h2 = CommandCanonicalizer.compute_hash("git commit -m")
        assert h1 == h2

    def test_different_patterns_different_hash(self):
        h1 = CommandCanonicalizer.compute_hash("git status")
        h2 = CommandCanonicalizer.compute_hash("git commit")
        assert h1 != h2

    def test_hash_is_8_chars(self):
        h = CommandCanonicalizer.compute_hash("git status")
        assert len(h) == 8

    def test_commits_with_different_messages_same_canonical(self):
        """Two git commits with different messages have the same canonical pattern."""
        c1 = CommandCanonicalizer.canonicalize('git commit -m "feat: x"')
        c2 = CommandCanonicalizer.canonicalize('git commit -m "fix: y"')
        assert c1 == c2


# ---------------------------------------------------------------------------
# lookup()
# ---------------------------------------------------------------------------


class TestLookup:
    def test_unknown_command_not_trusted(self, ledger):
        result = ledger.lookup("git status")
        assert result.is_trusted is False
        assert result.signature is None

    def test_known_command_is_trusted(self, ledger):
        ledger.record_success("git status")
        result = ledger.lookup("git status")
        assert result.is_trusted is True
        assert result.signature is not None

    def test_lookup_uses_canonical_pattern(self, ledger):
        """Commands with different literals but same canonical are trusted together."""
        ledger.record_success('git commit -m "feat: add x"')
        result = ledger.lookup('git commit -m "fix: critical bug"')
        assert result.is_trusted is True

    def test_lookup_result_has_reason(self, ledger):
        ledger.record_success("npm test")
        result = ledger.lookup("npm test")
        assert result.reason  # non-empty

    def test_lookup_result_trusted_has_signature(self, ledger):
        ledger.record_success("npm test")
        result = ledger.lookup("npm test")
        assert isinstance(result.signature, CommandSignature)

    def test_trust_level_once_always_prompts(self, ledger):
        """Commands with trust_level='once' are never auto-trusted."""
        ledger.record_success("risky-command", trust_level="once")
        result = ledger.lookup("risky-command")
        assert result.is_trusted is False
        assert result.signature is not None  # Exists in DB, but not auto-trusted


# ---------------------------------------------------------------------------
# record_success()
# ---------------------------------------------------------------------------


class TestRecordSuccess:
    def test_creates_new_entry(self, ledger):
        sig = ledger.record_success("git status")
        assert sig.canonical_pattern == "git status"
        assert sig.execution_count == 1
        assert sig.last_exit_code == 0

    def test_increments_count_on_repeated_calls(self, ledger):
        ledger.record_success("npm test")
        ledger.record_success("npm test")
        sig = ledger.record_success("npm test")
        assert sig.execution_count == 3

    def test_sudo_flag_set_correctly(self, ledger):
        sig = ledger.record_success("sudo apt install htop")
        assert sig.sudo_required is True

    def test_non_sudo_flag_false(self, ledger):
        sig = ledger.record_success("git status")
        assert sig.sudo_required is False

    def test_first_executed_at_preserved(self, ledger):
        sig1 = ledger.record_success("git status")
        sig2 = ledger.record_success("git status")
        assert sig1.first_executed_at == sig2.first_executed_at

    def test_last_executed_at_updated(self, ledger):
        import time
        sig1 = ledger.record_success("git status")
        time.sleep(0.01)
        sig2 = ledger.record_success("git status")
        # last_executed_at should be equal or later
        assert sig2.last_executed_at >= sig1.last_executed_at

    def test_trust_level_default_is_auto(self, ledger):
        sig = ledger.record_success("git status")
        assert sig.trust_level == "auto"

    def test_custom_trust_level_once(self, ledger):
        sig = ledger.record_success("git status", trust_level="once")
        assert sig.trust_level == "once"

    def test_command_hash_is_8_chars(self, ledger):
        sig = ledger.record_success("git status")
        assert len(sig.command_hash) == 8


# ---------------------------------------------------------------------------
# revoke()
# ---------------------------------------------------------------------------


class TestRevoke:
    def test_revoke_known_command_returns_true(self, ledger):
        ledger.record_success("git status")
        assert ledger.revoke("git status") is True

    def test_revoke_unknown_command_returns_false(self, ledger):
        assert ledger.revoke("nonexistent-command") is False

    def test_revoked_command_no_longer_trusted(self, ledger):
        ledger.record_success("git status")
        ledger.revoke("git status")
        result = ledger.lookup("git status")
        assert result.is_trusted is False

    def test_revoke_uses_canonical_pattern(self, ledger):
        """Revoking with a different literal (same canonical) works."""
        ledger.record_success('git commit -m "feat: x"')
        revoked = ledger.revoke('git commit -m "other message"')
        assert revoked is True
        assert ledger.lookup('git commit -m "yet another"').is_trusted is False


# ---------------------------------------------------------------------------
# list_trusted()
# ---------------------------------------------------------------------------


class TestListTrusted:
    def test_empty_ledger_returns_empty_list(self, ledger):
        assert ledger.list_trusted() == []

    def test_returns_all_entries(self, ledger):
        ledger.record_success("git status")
        ledger.record_success("npm test")
        ledger.record_success("pytest")
        entries = ledger.list_trusted()
        assert len(entries) == 3

    def test_entries_are_command_signatures(self, ledger):
        ledger.record_success("git status")
        entries = ledger.list_trusted()
        assert all(isinstance(e, CommandSignature) for e in entries)


# ---------------------------------------------------------------------------
# clear()
# ---------------------------------------------------------------------------


class TestClear:
    def test_clear_removes_all_entries(self, ledger):
        ledger.record_success("git status")
        ledger.record_success("npm test")
        count = ledger.clear()
        assert count == 2
        assert ledger.list_trusted() == []

    def test_clear_empty_ledger_returns_zero(self, ledger):
        assert ledger.clear() == 0


# ---------------------------------------------------------------------------
# Thread Safety (basic)
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_record_success_no_race(self, ledger):
        """Multiple threads recording the same command should not raise."""
        errors = []

        def record():
            try:
                for _ in range(10):
                    ledger.record_success("git status")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=record) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        # Final count should be 50 (5 threads × 10 records each)
        result = ledger.lookup("git status")
        assert result.is_trusted is True
        assert result.signature.execution_count == 50


# ---------------------------------------------------------------------------
# Security: Nuclear command invariant
# ---------------------------------------------------------------------------


class TestNuclearCommandInvariant:
    """The Trust Ledger itself doesn't know about nuclear commands —
    but the PEP must never call record_success() for nuclear commands.
    These tests verify the Trust Ledger's behavior if someone accidentally
    called record_success() with a nuclear command."""

    def test_nuclear_command_can_be_stored_if_called_directly(self, ledger):
        """If the ledger is called directly with a nuclear command, it stores it.
        The PEP is responsible for never calling this for nuclear commands."""
        # This is intentional — the ledger is dumb storage; PEP enforces the rule.
        sig = ledger.record_success("rm -rf /")
        assert sig is not None  # Stored without filtering

    def test_nuclear_command_would_be_trusted_if_stored(self, ledger):
        """Demonstrates why PEP must NEVER call record_success() for nuclear commands."""
        ledger.record_success("rm -rf /")
        result = ledger.lookup("rm -rf /")
        # It WOULD be trusted — confirming PEP's responsibility for filtering
        assert result.is_trusted is True
        # This is intentional by design — see PEP.record_action_success() for guard
