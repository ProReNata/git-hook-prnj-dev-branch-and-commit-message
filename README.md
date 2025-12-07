# What is this?
A script to be run by [pre-commit](https://pre-commit.com), to:
1. Enforce a branch naming standard that all branches should be named
   `[hotfix-]PRNJ-<number>-DEV-<number>-<description>`
2. Add the `PRNJ-<number>` and the `DEV-<number>` to the end of the commit
   message, or optionally just verify that they are there, based on an
   environment flag
3. Allow branches starting with `wip[-/]` or `hack[-/]` or `poc[-/]` to pass
   without following the naming standard.

## Development with uv

- Install tools (via mise): `mise install`
- Create/Sync venv with dev deps: `uv sync`
- Run tests: `uv run pytest`
- Lint/format with ruff: `uv run ruff check . && uv run ruff format .`

## FAQ
What if I want to commit code to a branch anyway?
: Then you can `SKIP=<hook name>` to tell `pre-commit` to skip this check.

Can I get the hook to just verify the commit message, not append IDs automatically?
: Yes, export set an environment flag `PRNJ_BRANCH_COMMIT_MSG_AUTO_APPEND=0`
