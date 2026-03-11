# Dev Workflow Decision — Laptop vs Server vs VS Code Remote SSH

**Date:** 2026-03-09
**Status:** Decision made / In progress
**Context:** Chat session, migrating from laptop-only dev to server-based dev

---

## Decision

Switching to VS Code Remote SSH on the-lab (192.168.5.10). Code is written
and committed directly on the server. Laptop becomes a thin UI terminal — it
renders the VS Code interface but all files, git operations, tests, and linting
run on the server. Fedora Server (headless) is correct for this setup — no
desktop GUI needed because VS Code Remote SSH handles the graphical layer.

## Credential approach

Fine-grained PAT (`orion-server-push`), scoped to `jeanpaul-source/orion` only,
permission `contents: write` + `metadata: read` (GitHub adds metadata automatically).
Expires 2027-01-01. Stored at `~/.config/git/credentials` on the server via
`credential.helper=store`. The `gh` OAuth token overrides were removed from
`~/.gitconfig` so the scoped PAT is what git actually uses — not the broad `gh` token.

## Tradeoff explicitly accepted

Dev environment and HAL runtime share a host. A host-level compromise is a
full compromise of both. Accepted because: the server is LAN-only, not
internet-exposed; branch protection on main requires CI to pass before any
merge; the merge button stays human; and `~/.config/git/credentials` is in
the Judge's `_SENSITIVE_PATHS` so HAL tools cannot read the PAT without
explicit operator approval.

## Docs updated

- CONTRIBUTING.md — "laptop pushes only" rule updated to reflect new workflow
- OPERATIONS.md — same

## Related changes made

- judge.py — ~/.config/git/credentials added to sensitive paths