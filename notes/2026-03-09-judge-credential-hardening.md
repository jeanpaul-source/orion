# Judge Hardening — Git Credential Path as Sensitive Path

**Date:** 2026-03-09
**Status:** Done — 2026-03-09
**Context:** Pre-requisite for storing a GitHub PAT on the server

---

## Problem

The Judge's sensitive paths list (~/.ssh, .env, /run/homelab-secrets, /etc/shadow)
does not include the git credential store location. If a fine-grained PAT is stored
at ~/.config/git/credentials or ~/.netrc, HAL tool calls targeting those paths
would not be automatically escalated.

## Fix

Add ~/.config/git/credentials, ~/.git-credentials, and ~/.netrc to _SENSITIVE_PATHS in hal/judge.py.

**File:** hal/judge.py
**Change:** One-line addition to the _SENSITIVE_PATHS tuple/list
**Tier effect:** Any read_file or run_command targeting those paths escalates by +1 tier
(tier 0 → 1, tier 1 → 2, etc.)

## Verification

1176 offline tests passed. `ruff check hal/judge.py` clean.

## Commit

fix: add git credential paths to Judge sensitive paths