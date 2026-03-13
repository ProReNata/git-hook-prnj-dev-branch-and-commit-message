import os
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from prnj_dev_branch_and_commit_message.__main__ import get_remote_repo_name, main

# Helpers


def run_cmd(
    runner: CliRunner,
    args: list[str],
    env: dict[str, str] | None = None,
) -> Result:
    # Ensure we don't simulate merge or rebase situations
    env_vars = {**os.environ, **(env or {})}
    return runner.invoke(main, args, env=env_vars)


def write_commit_msg(tmp_path: Path, content: str = "feat: something\n\nBody\n") -> Path:
    p = tmp_path / "COMMIT_EDITMSG"
    p.write_text(content)
    return p


@pytest.fixture(autouse=True)
def clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Default to auto-append on
    monkeypatch.delenv("PRNJ_BRANCH_COMMIT_MSG_AUTO_APPEND", raising=False)
    monkeypatch.delenv("TICKET_BRANCH_COMMIT_MSG_AUTO_APPEND", raising=False)
    # Clear PRE_COMMIT_COMMIT_MSG_SOURCE to behave like a normal commit
    monkeypatch.delenv("PRE_COMMIT_COMMIT_MSG_SOURCE", raising=False)


class TestBranchAndCommitMsgHooks:
    def test_project_branch_is_valid_name_but_blocks_commits(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        # proj/PRNJ-12345-description (no DEV) — valid project branch
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_branch_name_from_git",
            lambda: "proj/PRNJ-12345-description",
        )
        runner = CliRunner()
        msg_path = write_commit_msg(tmp_path)

        # Committing directly to project parent branch must be blocked
        res_branch = run_cmd(runner, ["check-branch", str(msg_path)])
        assert res_branch.exit_code != 0, "Commits must be rejected on project parent branches"

        # commit-msg: also reject at commit-msg stage for safety
        res_msg = run_cmd(runner, ["check-message", str(msg_path)])
        assert res_msg.exit_code != 0, "Commits must be rejected on project parent branches"

    def test_project_dev_branch_with_ticket_numbers_appends_ids(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        # proj/PRNJ-12345-DEV-54321-task-description
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_branch_name_from_git",
            lambda: "proj/PRNJ-12345-DEV-54321-implement-feature",
        )
        runner = CliRunner()
        msg_path = write_commit_msg(tmp_path, "feat: add X\n\nSome body\n")

        res = run_cmd(runner, ["check-message", str(msg_path)])
        assert res.exit_code == 0, res.output
        updated = msg_path.read_text()
        # Should contain both DEV and PRNJ on separate lines appended in body
        assert "\nDEV-54321\n" in updated
        assert "\nPRNJ-12345\n" in updated

    def test_project_dev_branch_without_dev_number_only_appends_prnj(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        # proj/PRNJ-12345-DEV-task-description (DEV, no number)
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_branch_name_from_git",
            lambda: "proj/PRNJ-12345-DEV-update-docs",
        )
        runner = CliRunner()
        msg_path = write_commit_msg(tmp_path, "chore: docs\n\nBody\n")

        res = run_cmd(runner, ["check-message", str(msg_path)])
        assert res.exit_code == 0, res.output
        updated = msg_path.read_text()
        assert "PRNJ-12345" in updated
        # Should NOT append DEV since there is no number in the branch
        assert "\nDEV\n" not in updated
        assert "DEV-" not in updated

    def test_hotfix_branch_allows_commits_and_requires_only_prnj(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        # Branch: hotfix/PRNJ-12345-description (no DEV)
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_branch_name_from_git",
            lambda: "hotfix/PRNJ-12345-urgent-fix",
        )
        runner = CliRunner()
        msg_path = write_commit_msg(tmp_path, "fix: urgent\n\nDetails\n")

        res = run_cmd(runner, ["check-branch", str(msg_path)])
        assert res.exit_code == 0, res.output

        res2 = run_cmd(runner, ["check-message", str(msg_path)])
        assert res2.exit_code == 0, res2.output
        updated = msg_path.read_text()
        # Should have PRNJ id appended, not DEV
        assert "PRNJ-12345" in updated
        assert "DEV" not in updated

    def test_task_branch_prnj_only(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        # Branch: PRNJ-12345-description (no prefix)
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_branch_name_from_git",
            lambda: "PRNJ-12345-refactor-modules",
        )
        runner = CliRunner()
        msg_path = write_commit_msg(tmp_path, "refactor: clean up\n\nBody\n")

        res = run_cmd(runner, ["check-branch", str(msg_path)])
        assert res.exit_code == 0, res.output

        res2 = run_cmd(runner, ["check-message", str(msg_path)])
        assert res2.exit_code == 0, res2.output
        updated = msg_path.read_text()
        # Should append PRNJ only
        assert "PRNJ-12345" in updated
        assert "DEV" not in updated


class TestNonPrnjPrefixes:
    """Non-PRNJ ticket prefixes work correctly."""

    def test_flow_prefix_branch(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_branch_name_from_git",
            lambda: "FLOW-789-DEV-101-feature",
        )
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_remote_repo_name",
            lambda: None,
        )
        runner = CliRunner()
        msg_path = write_commit_msg(tmp_path, "feat: new feature\n\nBody\n")

        res = run_cmd(runner, ["check-message", str(msg_path)])
        assert res.exit_code == 0, res.output
        updated = msg_path.read_text()
        assert "FLOW-789" in updated
        assert "DEV-101" in updated

    def test_lf_prefix_branch(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_branch_name_from_git",
            lambda: "LF-42-DEV-7-bugfix",
        )
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_remote_repo_name",
            lambda: None,
        )
        runner = CliRunner()
        msg_path = write_commit_msg(tmp_path, "fix: bug\n\nBody\n")

        res = run_cmd(runner, ["check-message", str(msg_path)])
        assert res.exit_code == 0, res.output
        updated = msg_path.read_text()
        assert "LF-42" in updated
        assert "DEV-7" in updated

    def test_kli_prefix_branch(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_branch_name_from_git",
            lambda: "KLI-1-fix",
        )
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_remote_repo_name",
            lambda: None,
        )
        runner = CliRunner()
        msg_path = write_commit_msg(tmp_path, "fix: something\n\nBody\n")

        res = run_cmd(runner, ["check-branch", str(msg_path)])
        assert res.exit_code == 0, res.output


class TestRemotePrefixEnforcement:
    """Remote-based prefix validation."""

    def test_matching_prefix_passes(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_branch_name_from_git",
            lambda: "PRNJ-123-DEV-1-feature",
        )
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_remote_repo_name",
            lambda: "prorenatajournal",
        )
        runner = CliRunner()
        msg_path = write_commit_msg(tmp_path)

        res = run_cmd(runner, ["check-branch", str(msg_path)])
        assert res.exit_code == 0, res.output

    def test_mismatched_prefix_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_branch_name_from_git",
            lambda: "FLOW-123-DEV-1-feature",
        )
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_remote_repo_name",
            lambda: "prorenatajournal",
        )
        runner = CliRunner()
        msg_path = write_commit_msg(tmp_path)

        res = run_cmd(runner, ["check-branch", str(msg_path)])
        assert res.exit_code != 0
        assert "requires ticket prefix 'PRNJ'" in res.output
        assert "but branch uses 'FLOW'" in res.output

    def test_unknown_remote_allows_any_prefix(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_branch_name_from_git",
            lambda: "XYZ-99-DEV-1-feature",
        )
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_remote_repo_name",
            lambda: "some-other-repo",
        )
        runner = CliRunner()
        msg_path = write_commit_msg(tmp_path)

        res = run_cmd(runner, ["check-branch", str(msg_path)])
        assert res.exit_code == 0, res.output

    def test_no_remote_allows_any_prefix(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_branch_name_from_git",
            lambda: "XYZ-99-DEV-1-feature",
        )
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_remote_repo_name",
            lambda: None,
        )
        runner = CliRunner()
        msg_path = write_commit_msg(tmp_path)

        res = run_cmd(runner, ["check-branch", str(msg_path)])
        assert res.exit_code == 0, res.output

    def test_case_insensitive_repo_matching(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_branch_name_from_git",
            lambda: "PRNJ-123-DEV-1-feature",
        )
        # get_remote_repo_name() already casefolds, so simulate that
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_remote_repo_name",
            lambda: "prorenatajournal",  # casefolded from "ProRenataJournal"
        )
        runner = CliRunner()
        msg_path = write_commit_msg(tmp_path)

        res = run_cmd(runner, ["check-branch", str(msg_path)])
        assert res.exit_code == 0, res.output

    def test_flow_prefix_on_prorenataflow_repo(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_branch_name_from_git",
            lambda: "FLOW-456-DEV-1-feature",
        )
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_remote_repo_name",
            lambda: "prorenataflow",
        )
        runner = CliRunner()
        msg_path = write_commit_msg(tmp_path)

        res = run_cmd(runner, ["check-branch", str(msg_path)])
        assert res.exit_code == 0, res.output


class TestEnvVarBackwardCompat:
    """Both env var names work for disabling auto-append."""

    def test_new_env_var_disables_auto_append(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_branch_name_from_git",
            lambda: "PRNJ-12345-DEV-1-feature",
        )
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_remote_repo_name",
            lambda: None,
        )
        runner = CliRunner()
        msg_path = write_commit_msg(tmp_path, "feat: test\n\nPRNJ-12345\nDEV-1\n")

        res = run_cmd(
            runner,
            ["check-message", str(msg_path)],
            env={"TICKET_BRANCH_COMMIT_MSG_AUTO_APPEND": "0"},
        )
        assert res.exit_code == 0, res.output

    def test_legacy_env_var_disables_auto_append(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_branch_name_from_git",
            lambda: "PRNJ-12345-DEV-1-feature",
        )
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_remote_repo_name",
            lambda: None,
        )
        runner = CliRunner()
        msg_path = write_commit_msg(tmp_path, "feat: test\n\nPRNJ-12345\nDEV-1\n")

        res = run_cmd(
            runner,
            ["check-message", str(msg_path)],
            env={"PRNJ_BRANCH_COMMIT_MSG_AUTO_APPEND": "0"},
        )
        assert res.exit_code == 0, res.output

    def test_new_env_var_takes_precedence(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_branch_name_from_git",
            lambda: "PRNJ-12345-DEV-1-feature",
        )
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_remote_repo_name",
            lambda: None,
        )
        runner = CliRunner()
        # Message already has IDs so validation passes regardless
        msg_path = write_commit_msg(tmp_path, "feat: test\n\nPRNJ-12345\nDEV-1\n")

        # New var says enable (not "0"), legacy says disable — new wins
        res = run_cmd(
            runner,
            ["check-message", str(msg_path)],
            env={
                "TICKET_BRANCH_COMMIT_MSG_AUTO_APPEND": "1",
                "PRNJ_BRANCH_COMMIT_MSG_AUTO_APPEND": "0",
            },
        )
        assert res.exit_code == 0, res.output


class TestGetRemoteRepoName:
    """Unit tests for URL parsing in get_remote_repo_name."""

    def test_https_url_with_git_suffix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            subprocess,
            "check_output",
            lambda *_args, **_kwargs: "https://github.com/org/ProRenataJournal.git\n",
        )
        assert get_remote_repo_name() == "prorenatajournal"

    def test_https_url_without_git_suffix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            subprocess,
            "check_output",
            lambda *_args, **_kwargs: "https://github.com/org/klinta\n",
        )
        assert get_remote_repo_name() == "klinta"

    def test_ssh_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            subprocess,
            "check_output",
            lambda *_args, **_kwargs: "git@github.com:org/lerkaka-foundation.git\n",
        )
        assert get_remote_repo_name() == "lerkaka-foundation"

    def test_no_remote_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def raise_error(*_args: object, **_kwargs: object) -> None:
            raise subprocess.CalledProcessError(1, "git")

        monkeypatch.setattr(subprocess, "check_output", raise_error)
        assert get_remote_repo_name() is None
