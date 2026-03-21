# Contributing

This repository is a failure-sensitive, stateful media management engine.

Read [AGENTS.md](AGENTS.md) first. It defines non-negotiable runtime invariants and safety constraints.

## Scope

This file defines the default contribution workflow for humans and agents:

- branch creation
- pull request lifecycle
- review expectations
- merge and cleanup

For documentation-only changes under `documentation/`, also follow `documentation/LOCAL_INSTRUCTIONS.md`.

## Preconditions

Before starting work:

1. Ensure your local `develop` is up to date.
2. Confirm `gh auth status` is valid for PR operations.
3. Confirm your change plan does not violate `AGENTS.md` invariants.
4. Check `git status --porcelain` before using `develop` as a base branch.
5. If `develop` has uncommitted changes, stop and either commit, stash, or move that work before starting a new contribution.

## Standard GitHub Flow

### 1) Create a Feature Branch

Use `develop` as the base branch.

Example:

```bash
git status --porcelain
git fetch origin
git checkout develop
git pull --ff-only origin develop
git checkout -b feature/<short-kebab-description>
```

Do not implement or commit work directly on `develop`, even when the worktree is clean.

Branch naming guidance:

- `feature/<description>` for new functionality
- `fix/<description>` for bug fixes
- `docs/<description>` for documentation-only updates
- `chore/<description>` for maintenance work

### 2) Implement and Validate

Run checks relevant to your change scope before committing.

Examples:

```bash
./.venv/bin/python -m pytest
./.venv/bin/mkdocs build --strict
```

If your change is narrow, run targeted tests plus any required safety/invariant checks.

### 3) Commit Changes

Commit only intended files.

Example:

```bash
git add <files>
git commit -m "docs: expand CLI command reference"
```

Recommended commit style:

- `feat: ...`
- `fix: ...`
- `docs: ...`
- `chore: ...`
- `refactor: ...`
- `test: ...`

### 4) Push Branch

```bash
git push -u origin <feature-branch>
```

### 5) Raise Pull Request to `develop`

Use `gh`:

```bash
gh pr create --base develop --head <feature-branch> --title "<type>: <short title>" --body "<structured summary>"
```

PR description should include:

- problem statement
- summary of changes
- invariants/risk analysis
- tests/checks run with outcomes
- rollback notes (if applicable)

## Senior Review Expectations

Review from a senior-engineer perspective:

1. Correctness against requirements.
2. Invariant safety (`AGENTS.md` compliance).
3. Regression risk and edge-case handling.
4. Idempotency/restart and failure semantics for behavior changes.
5. Test coverage and documentation coverage.

If changes are needed:

- add PR comments via `gh pr comment` (or `gh api` review endpoints)
- push follow-up commits to the same branch
- summarize fixes in the PR conversation

If `gh` review calls are rate-limited, record the limitation in the PR and continue with explicit local review notes.

## Merge Rules

Merge into `develop` only when:

1. Required checks pass (or approved exceptions are documented).
2. No unresolved critical review findings remain.
3. The PR is mergeable.

Preferred merge strategy:

```bash
gh pr merge <pr-number> --squash
```

Use a different strategy only if repository policy for that PR requires it.

## Branch and Release Strategy

Branch roles:

- `main` contains stable releases only.
- `develop` is the integration branch for ongoing work.
- `feature/*` branches are short-lived branches created from `develop`.

Release workflow:

1. Complete and validate work on `develop`.
2. Merge `develop` into `main` using a non-fast-forward merge.
3. Create an annotated version tag on the release commit in `main`.
4. Continue new work from `develop` or a fresh `feature/*` branch.

## Branch Cleanup

Cleanup only after confirming merge:

```bash
git checkout develop
git pull --ff-only origin develop
git branch -d <feature-branch>
git push origin --delete <feature-branch>
```

Do not delete a branch if:

- PR is not merged
- branch is still needed for follow-up work
- cleanup would remove unreleased or unreviewed work

## Required Final Summary (for agent-driven changes)

When finishing a contribution cycle, include:

1. branch name
2. PR number and URL
3. merge commit SHA
4. checks/tests run and outcomes
5. review findings and resolutions
6. whether PR comments were posted
7. branch cleanup status (local and remote)
8. concise lessons learned
