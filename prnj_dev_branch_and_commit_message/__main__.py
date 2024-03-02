import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

import click


class Branch(NamedTuple):
    branch_name: str
    is_wip_hack: bool = False
    is_hotfix: bool = False
    prnj: str | None = None
    dev: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.is_wip_hack or bool(self.prnj and self.dev)


def get_branch_name_from_git() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        encoding="utf-8",
    ).strip()


def get_branch() -> Branch:
    branch_name = get_branch_name_from_git()
    if not branch_name:
        print("Could not find branch name.")
        return Branch("")

    if branch_name.startswith(("wip-", "wip/", "hack-", "hack/")):
        return Branch(branch_name, is_wip_hack=True)

    match = re.match(r"(?P<hotfix>hotfix-)?(?P<prnj>PRNJ-\d+)-(?P<dev>DEV-\d+)-\w+", branch_name)
    if not match:
        print("Branch name does not follow the standard.", file=sys.stderr)
        return Branch(branch_name)

    is_hotfix = bool(match["hotfix"])
    return Branch(branch_name, is_hotfix=is_hotfix, prnj=match["prnj"], dev=match["dev"])


def append_to_commit_msg() -> None:
    branch = get_branch()

    if branch.prnj and branch.dev:
        with open("COMMIT_EDITMSG", "a") as f:
            f.write(f"\n{branch.dev}\n{branch.prnj}")


@click.group()
def cli() -> None:
    branch = get_branch()
    if not branch.is_valid:
        sys.exit(1)


@cli.command("prepare")
def prepare_commit_msg() -> None:
    if os.getenv("PRNJ_BRANCH_COMMIT_MSG_AUTO_APPEND") == "1":
        append_to_commit_msg()


@cli.command("commit")
def commit_msg() -> None:
    msg = Path("COMMIT_EDITMSG").read_text()
    subject, _, body = msg.partition("\n")
    branch = get_branch()
    if branch.prnj and branch.prnj not in body:
        print(f"Did not find {branch.prnj} in commit message body")
        sys.exit(1)
    if branch.dev and branch.dev not in body:
        print(f"Did not find {branch.dev} in commit message body")
        sys.exit(1)


if __name__ == "__main__":
    cli()
