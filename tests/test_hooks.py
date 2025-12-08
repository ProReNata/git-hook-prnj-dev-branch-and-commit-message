import os
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from prnj_dev_branch_and_commit_message.__main__ import main

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
    # Clear PRE_COMMIT_COMMIT_MSG_SOURCE to behave like a normal commit
    monkeypatch.delenv("PRE_COMMIT_COMMIT_MSG_SOURCE", raising=False)


class TestBranchAndCommitMsgHooks:
    def test_project_branch_is_valid_name_but_blocks_commits(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        # Branch: proj/PRNJ-12345-description (no DEV). Should be a valid project branch.
        monkeypatch.setattr(
            "prnj_dev_branch_and_commit_message.__main__.get_branch_name_from_git",
            lambda: "proj/PRNJ-12345-description",
        )
        runner = CliRunner()
        msg_path = write_commit_msg(tmp_path)

        # prepare-commit-msg: committing directly to project parent branch must be blocked
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
        # Branch: proj/PRNJ-12345-DEV-54321-task-description
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
        # Branch: proj/PRNJ-12345-DEV-task-description (DEV marker without number)
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
