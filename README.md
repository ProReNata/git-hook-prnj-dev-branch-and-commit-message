# What is this?
A script to be run by [pre-commit](https://pre-commit.com), to:
1. Enforce a branch naming standard that all branches should be named
   `[hotfix-]PRNJ-<number>-DEV-<number>-<description>`
2. Add the `PRNJ-<number>` and the `DEV-<number>` to the end of the commit
   message, or optionally just verify that they are there, based on an
   environment flag
3. Allow branches starting with `wip[-/]` or `hack[-/]` to pass without
   following the naming standard.

## FAQ
What if I want to commit code to a branch anyway?
: Then you can `SKIP=<hook name>` to tell `pre-commit` to skip this check.

What is the environment flag called?
: It's called `PRNJ_BRANCH_COMMIT_MSG_AUTO_APPEND`
