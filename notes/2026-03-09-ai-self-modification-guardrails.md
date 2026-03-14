# AI Self-Modification Guardrails — Analysis and Boundaries

**Date:** 2026-03-09
**Status:** Analysis only — no changes yet

---

## The core problem

The system that gates HAL's actions (the Judge) can be modified by HAL.
This is a circularity: the gate could weaken itself. The test suite catches
broken code but not malicious-but-valid code.

## What HAL can currently do to its own codebase

- write_file to hal/*.py — Judge tier 2, requires explicit approval in REPL,
  auto-denied via HTTP/Telegram
- git add/commit — blocked by _GIT_WRITE_SUBCOMMANDS in Judge
- git push — blocked; no push credentials currently on server

## What the safe model looks like long-term

HAL proposes → human reviews → human merges.
HAL never: pushes directly to main, restarts itself after a self-edit,
modifies judge.py without a PR.

## Guardrails that exist today

- ServerJudge auto-denies tier 1+ (HTTP/Telegram can't do self-edits)
- _GIT_WRITE_SUBCOMMANDS blocks commit/push/rebase etc. via Judge
- Branch protection requires CI to pass before merge
- write_file to hal/ is tier 2 — requires REPL approval

## Guardrails that don't exist yet (future work)

- [ ] HAL's PRs flagged as AI-authored for extra scrutiny
- [ ] Dedicated "staging" run before a self-edit goes to production
- [ ] judge.py itself as a protected file requiring tier 3 (not just tier 2)

## The one never-cross line

HAL does not gain the ability to merge its own PRs. The merge button stays human.