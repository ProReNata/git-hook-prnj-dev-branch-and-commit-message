from __future__ import annotations

import os
import re
import subprocess
from dataclasses import InitVar, dataclass, field
from enum import Enum
from pathlib import Path
from typing import NamedTuple

import click

PRNJ = r"(?P<prnj>PRNJ-\d+)"
DEV = r"(?P<dev>DEV(?:-\d+)?)"
HOTFIX = r"(?P<hotfix>hotfix-)"


class Branch(NamedTuple):
    branch_name: str
    is_wip_hack: bool = False
    is_hotfix: bool = False
    prnj: str | None = None
    dev: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.is_wip_hack or bool(self.prnj and self.dev)

    @property
    def is_dev_without_number(self) -> bool:
        return self.dev is not None and self.dev == "DEV"


class MessageSource(Enum):
    MESSAGE = "message"
    TEMPLATE = "template"
    MERGE = "merge"
    SQUASH = "squash"
    COMMIT = "commit"
    NONE = ""

    @property
    def is_merge(self) -> bool:
        return self == MessageSource.MERGE


def get_branch_name_from_git() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        encoding="utf-8",
    ).strip()


def get_branch() -> Branch:
    branch_name = get_branch_name_from_git()

    if branch_name.startswith(("wip-", "wip/", "hack-", "hack/", "poc-", "poc/")):
        return Branch(branch_name, is_wip_hack=True)

    match = re.match(
        rf"{HOTFIX}?{PRNJ}-{DEV}-\w+",
        branch_name,
    )
    if not match:
        found_prnj = bool(re.search(rf"{PRNJ}", branch_name))
        found_dev = bool(re.search(rf"{DEV}", branch_name))
        no_description = bool(re.match(rf"{HOTFIX}?{PRNJ}-{DEV}$", branch_name))

        error_msg = []
        if not found_prnj:
            error_msg.append("could not find PRNJ-number")
        if not found_dev:
            error_msg.append("could not find DEV number or marker")
        if no_description:
            error_msg.append("could not find a branch description")
        elif found_prnj and found_dev:
            error_msg.append(
                "PRNJ-number and DEV are wrongly placed: "
                "They should be (hotfix)?-PRNJ-number-DEV-number?-message"
            )

        raise click.ClickException(
            "Branch name does not follow the standard: {}".format(", ".join(error_msg)),
        )

    is_hotfix = bool(match["hotfix"])
    return Branch(branch_name, is_hotfix=is_hotfix, prnj=match["prnj"], dev=match["dev"])


def test(command: str | list[str]) -> bool:
    try:
        # Capture the output, even if we don't use it.
        subprocess.check_output(command, shell=isinstance(command, str))
    except subprocess.CalledProcessError:
        return False
    else:
        return True


def get_message_source() -> MessageSource:
    commit_msg_src = os.environ.get("PRE_COMMIT_COMMIT_MSG_SOURCE")
    if (
        test("git rev-parse -q --verify MERGE_HEAD")
        or test("git rev-parse -q --verify REBASE_HEAD")
        or test("git rev-parse -q --verify CHERRY_PICK_HEAD")
    ):
        commit_msg_src = "merge"

    try:
        message_source = MessageSource(commit_msg_src)
    except (TypeError, ValueError):
        message_source = MessageSource("")

    return message_source


@dataclass
class CommitMessage:
    branch: InitVar[Branch]
    message: str
    subject: str = field(init=False)
    body: str = field(init=False)
    rest: str = field(init=False)
    prnj_found: bool = field(init=False)
    dev_found: bool = field(init=False)

    def __post_init__(self, branch: Branch) -> None:
        commit_msg_subject, _, below_subject = self.message.partition("\n")

        # Find the scissor, and add the IDs after the first
        # non-comment line above that.
        m = re.search(
            r"^# ------------------------ >8 ------------------------",
            below_subject,
            re.MULTILINE,
        )
        if m:
            break_location = m.start(0)
            commit_msg_body, commit_msg_rest = (
                below_subject[:break_location],
                below_subject[break_location:],
            )
        else:
            commit_msg_body, commit_msg_rest = below_subject, ""

        self.subject = commit_msg_subject
        self.body = commit_msg_body
        self.rest = commit_msg_rest
        self.prnj_found = bool(
            branch.prnj and re.search("^" + branch.prnj, commit_msg_body, re.MULTILINE)
        )
        self.dev_found = bool(
            branch.dev and re.search("^" + branch.dev, commit_msg_body, re.MULTILINE)
        )


def validate_commit_msg_body(commit_message_filename: str) -> tuple[Branch, CommitMessage]:
    branch = get_branch()
    commit_msg = Path(commit_message_filename).read_text()
    return branch, CommitMessage(branch, commit_msg)


def append_to_commit_msg(commit_message_filename: str) -> None:
    branch, commit_msg = validate_commit_msg_body(commit_message_filename)
    if branch.is_wip_hack:
        return
    if commit_msg.prnj_found and branch.is_dev_without_number or commit_msg.dev_found:
        return

    # We _should_ be guaranteed to have these here, but mypy and
    # a bad `Branch` type ….
    if branch.prnj and branch.dev:
        parts = []
        if not (branch.is_dev_without_number or commit_msg.dev_found):
            parts.append(branch.dev)
        if not commit_msg.prnj_found:
            parts.append(branch.prnj)

        ids_to_append = "\n".join(parts)

        with Path(commit_message_filename).open("w") as f:
            print(commit_msg.subject, file=f)
            print(commit_msg.body, file=f)
            print(f"\n{ids_to_append}", file=f)
            print(commit_msg.rest, file=f)


@click.group()
def main() -> None:
    pass


@main.command(name="check-branch")
@click.argument("commit_msg_filename")
def check_branch(commit_msg_filename: str) -> None:
    message_source = get_message_source()
    if message_source.is_merge:
        return

    _ = get_branch()


@main.command(name="check-message")
@click.argument("commit_msg_filename")
def check_message(commit_msg_filename: str) -> None:
    message_source = get_message_source()
    if message_source.is_merge:
        return

    if os.getenv("PRNJ_BRANCH_COMMIT_MSG_AUTO_APPEND") != "0":
        append_to_commit_msg(commit_msg_filename)
    branch, commit_msg = validate_commit_msg_body(commit_msg_filename)
    if branch.is_wip_hack:
        return

    if not commit_msg.prnj_found:
        raise click.ClickException(f"Did not find {branch.prnj} in commit message body")
    if not (branch.is_dev_without_number or commit_msg.dev_found):
        raise click.ClickException(f"Did not find {branch.dev} in commit message body")


if __name__ == "__main__":
    main()
