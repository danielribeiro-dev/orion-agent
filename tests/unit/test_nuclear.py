"""
Tests for NuclearSafetyGate (v0.3.0 Sprint 4)

Covers:
  - BlastRadiusClassifier: classification of all blast radius levels
  - NuclearSafetyGate.challenge(): non-nuclear commands pass through
  - NuclearSafetyGate.challenge(): nuclear commands trigger auth challenge
  - NuclearSafetyGate.assert_authorized(): raises NuclearAuthDenied on failure
  - Authentication methods: see test_nuclear_auth.py (polkit/PAM, v0.5.3)
  - NuclearAuthDenied exception attributes
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from orion.governance.nuclear import (
    BlastRadius,
    BlastRadiusClassifier,
    NuclearAuthDenied,
    NuclearChallengeResult,
    NuclearSafetyGate,
)

# ---------------------------------------------------------------------------
# BlastRadiusClassifier
# ---------------------------------------------------------------------------


class TestBlastRadiusClassifier:
    """Tests for the command blast radius classifier."""

    def test_git_status_is_benign(self):
        assert BlastRadiusClassifier.classify("git status") == BlastRadius.BENIGN

    def test_npm_test_is_benign(self):
        assert BlastRadiusClassifier.classify("npm test") == BlastRadius.BENIGN

    def test_pytest_is_benign(self):
        assert BlastRadiusClassifier.classify("pytest tests/") == BlastRadius.BENIGN

    def test_cat_file_is_benign(self):
        assert BlastRadiusClassifier.classify("cat README.md") == BlastRadius.BENIGN

    def test_ls_is_benign(self):
        assert BlastRadiusClassifier.classify("ls -la") == BlastRadius.BENIGN

    # --- WORKSPACE_MUTATION ---

    def test_mkdir_is_mutation(self):
        assert BlastRadiusClassifier.classify("mkdir -p src/components") == BlastRadius.WORKSPACE_MUTATION

    def test_touch_is_mutation(self):
        assert BlastRadiusClassifier.classify("touch newfile.py") == BlastRadius.WORKSPACE_MUTATION

    def test_mv_is_mutation(self):
        assert BlastRadiusClassifier.classify("mv old.py new.py") == BlastRadius.WORKSPACE_MUTATION

    def test_cp_is_mutation(self):
        assert BlastRadiusClassifier.classify("cp src dest") == BlastRadius.WORKSPACE_MUTATION

    # --- SYSTEM_ELEVATED ---

    def test_sudo_apt_install_is_elevated(self):
        result = BlastRadiusClassifier.classify("sudo apt install htop")
        assert result == BlastRadius.SYSTEM_ELEVATED

    def test_sudo_systemctl_restart_is_elevated(self):
        result = BlastRadiusClassifier.classify("sudo systemctl restart nginx")
        assert result == BlastRadius.SYSTEM_ELEVATED

    def test_sudo_apt_update_is_elevated(self):
        result = BlastRadiusClassifier.classify("sudo apt-get update")
        assert result == BlastRadius.SYSTEM_ELEVATED

    # --- NUCLEAR_DESTRUCTIVE ---

    def test_rm_rf_is_nuclear(self):
        assert BlastRadiusClassifier.classify("rm -rf /tmp/cache") == BlastRadius.NUCLEAR_DESTRUCTIVE

    def test_rm_fr_is_nuclear(self):
        assert BlastRadiusClassifier.classify("rm -fr /var/log") == BlastRadius.NUCLEAR_DESTRUCTIVE

    def test_rm_rf_root_is_nuclear(self):
        assert BlastRadiusClassifier.classify("rm -rf /") == BlastRadius.NUCLEAR_DESTRUCTIVE

    def test_mkfs_is_nuclear(self):
        assert BlastRadiusClassifier.classify("mkfs.ext4 /dev/sda1") == BlastRadius.NUCLEAR_DESTRUCTIVE

    def test_dd_to_device_is_nuclear(self):
        assert BlastRadiusClassifier.classify("dd if=/dev/zero of=/dev/sda") == BlastRadius.NUCLEAR_DESTRUCTIVE

    def test_shred_is_nuclear(self):
        assert BlastRadiusClassifier.classify("shred -n 3 /dev/sda") == BlastRadius.NUCLEAR_DESTRUCTIVE

    def test_wipe_is_nuclear(self):
        assert BlastRadiusClassifier.classify("wipe /dev/sdb") == BlastRadius.NUCLEAR_DESTRUCTIVE

    def test_rm_etc_passwd_is_nuclear(self):
        assert BlastRadiusClassifier.classify("rm /etc/passwd") == BlastRadius.NUCLEAR_DESTRUCTIVE

    def test_chmod_ssh_is_nuclear(self):
        assert BlastRadiusClassifier.classify("chmod 777 ~/.ssh/id_rsa") == BlastRadius.NUCLEAR_DESTRUCTIVE

    def test_sudo_rm_is_nuclear(self):
        assert BlastRadiusClassifier.classify("sudo rm -rf /var") == BlastRadius.NUCLEAR_DESTRUCTIVE

    def test_git_clean_fd_is_nuclear(self):
        assert BlastRadiusClassifier.classify("git clean -fd") == BlastRadius.NUCLEAR_DESTRUCTIVE

    def test_is_nuclear_convenience_method(self):
        assert BlastRadiusClassifier.is_nuclear("rm -rf /") is True
        assert BlastRadiusClassifier.is_nuclear("git status") is False
        assert BlastRadiusClassifier.is_nuclear("sudo apt install htop") is False

    def test_classify_case_insensitive(self):
        """Classification is case-insensitive."""
        assert BlastRadiusClassifier.classify("RM -RF /TMP") == BlastRadius.NUCLEAR_DESTRUCTIVE


# ---------------------------------------------------------------------------
# NuclearSafetyGate — Non-Nuclear Commands
# ---------------------------------------------------------------------------


class TestNuclearGateNonNuclear:
    """Non-nuclear commands pass through without authentication."""

    def setup_method(self):
        self.gate = NuclearSafetyGate()

    def test_benign_command_passes_without_auth(self):
        result = self.gate.challenge("git status")
        assert result.authorized is True
        assert result.method_used == "no_auth_required"
        assert result.duration_seconds == 0.0

    def test_elevated_command_passes_without_nuclear_auth(self):
        result = self.gate.challenge("sudo apt install htop")
        assert result.authorized is True
        assert result.method_used == "no_auth_required"

    def test_mutation_command_passes_without_nuclear_auth(self):
        result = self.gate.challenge("mkdir -p src/new")
        assert result.authorized is True
        assert result.method_used == "no_auth_required"

    def test_result_includes_blast_radius(self):
        result = self.gate.challenge("git status")
        assert result.blast_radius == BlastRadius.BENIGN

    def test_assert_authorized_does_not_raise_for_benign(self):
        # Should not raise
        result = self.gate.assert_authorized("git status")
        assert result.authorized is True


# ---------------------------------------------------------------------------
# NuclearSafetyGate — Nuclear Commands (mocked auth)
# ---------------------------------------------------------------------------


class TestNuclearGateNuclear:
    """Nuclear commands require OS authentication."""

    def setup_method(self):
        self.gate = NuclearSafetyGate()

    def test_nuclear_command_triggers_challenge(self):
        with patch.object(self.gate, "_run_challenge") as mock_challenge:
            mock_challenge.return_value = NuclearChallengeResult(
                authorized=True,
                method_used="zenity",
                duration_seconds=1.5,
                command_pattern="rm -rf /tmp",
                blast_radius=BlastRadius.NUCLEAR_DESTRUCTIVE,
            )
            result = self.gate.challenge("rm -rf /tmp")
            mock_challenge.assert_called_once()
            assert result.authorized is True

    def test_nuclear_command_denied_when_auth_cancelled(self):
        with patch.object(self.gate, "_run_challenge") as mock_challenge:
            mock_challenge.return_value = NuclearChallengeResult(
                authorized=False,
                method_used="zenity",
                duration_seconds=2.0,
                command_pattern="rm -rf /",
                blast_radius=BlastRadius.NUCLEAR_DESTRUCTIVE,
            )
            result = self.gate.challenge("rm -rf /")
            assert result.authorized is False

    def test_assert_authorized_raises_when_denied(self):
        with patch.object(self.gate, "_run_challenge") as mock_challenge:
            mock_challenge.return_value = NuclearChallengeResult(
                authorized=False,
                method_used="zenity",
                duration_seconds=0.5,
                command_pattern="rm -rf /",
                blast_radius=BlastRadius.NUCLEAR_DESTRUCTIVE,
            )
            with pytest.raises(NuclearAuthDenied) as exc_info:
                self.gate.assert_authorized("rm -rf /")
            assert exc_info.value.blast_radius == BlastRadius.NUCLEAR_DESTRUCTIVE
            assert exc_info.value.method_used == "zenity"

    def test_assert_authorized_returns_result_when_approved(self):
        with patch.object(self.gate, "_run_challenge") as mock_challenge:
            mock_challenge.return_value = NuclearChallengeResult(
                authorized=True,
                method_used="tty_fallback",
                duration_seconds=3.0,
                command_pattern="rm -rf /tmp",
                blast_radius=BlastRadius.NUCLEAR_DESTRUCTIVE,
            )
            result = self.gate.assert_authorized("rm -rf /tmp")
            assert result.authorized is True

    def test_requires_nuclear_auth_true_for_nuclear(self):
        assert self.gate.requires_nuclear_auth("rm -rf /") is True

    def test_requires_nuclear_auth_false_for_benign(self):
        assert self.gate.requires_nuclear_auth("git status") is False


# ---------------------------------------------------------------------------
# NuclearAuthDenied Exception
# ---------------------------------------------------------------------------


class TestNuclearAuthDenied:
    def test_attributes_set_correctly(self):
        exc = NuclearAuthDenied(
            command="rm -rf /",
            blast_radius=BlastRadius.NUCLEAR_DESTRUCTIVE,
            method_used="zenity",
        )
        assert exc.command == "rm -rf /"
        assert exc.blast_radius == BlastRadius.NUCLEAR_DESTRUCTIVE
        assert exc.method_used == "zenity"

    def test_error_message_includes_command(self):
        exc = NuclearAuthDenied(
            command="rm -rf /",
            blast_radius=BlastRadius.NUCLEAR_DESTRUCTIVE,
            method_used="zenity",
        )
        assert "rm -rf /" in str(exc)

    def test_error_message_includes_blast_radius(self):
        exc = NuclearAuthDenied(
            command="rm -rf /",
            blast_radius=BlastRadius.NUCLEAR_DESTRUCTIVE,
            method_used="tty_fallback",
        )
        assert "nuclear" in str(exc).lower()

    def test_error_message_indicates_denial(self):
        exc = NuclearAuthDenied(
            command="rm -rf /",
            blast_radius=BlastRadius.NUCLEAR_DESTRUCTIVE,
            method_used="zenity",
        )
        # Should contain some indication the action was denied/cancelled
        assert any(word in str(exc).lower() for word in ["denied", "negada", "cancelada", "cancelled"])


# ---------------------------------------------------------------------------
# NuclearChallengeResult
# ---------------------------------------------------------------------------


class TestNuclearChallengeResult:
    def test_result_is_immutable(self):
        result = NuclearChallengeResult(
            authorized=True,
            method_used="zenity",
            duration_seconds=1.0,
            command_pattern="rm -rf /tmp",
            blast_radius=BlastRadius.NUCLEAR_DESTRUCTIVE,
        )
        with pytest.raises(Exception):
            result.authorized = False  # type: ignore

    def test_all_fields_accessible(self):
        result = NuclearChallengeResult(
            authorized=False,
            method_used="tty_fallback",
            duration_seconds=5.2,
            command_pattern="wipe /dev/sdb",
            blast_radius=BlastRadius.NUCLEAR_DESTRUCTIVE,
        )
        assert result.authorized is False
        assert result.method_used == "tty_fallback"
        assert result.duration_seconds == pytest.approx(5.2)
        assert result.blast_radius == BlastRadius.NUCLEAR_DESTRUCTIVE
