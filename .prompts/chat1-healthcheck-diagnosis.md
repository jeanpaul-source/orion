# Task: Phase 1 — Clean up healthcheck fix + diagnose live system

## Who I am

I'm learning to code. This project was largely AI-built and I'm trying to
understand what's real, what's broken, and get it into a solid state. Explain
what you're doing and why as you go.

## Project protocols

Read these FIRST before making any changes — they are mandatory:

- `memory/SUMMARY.md` — current project state
- `.github/copilot-instructions.md` — how to work on this codebase

Key rules:

1. Root cause first — state what's actually wrong before changing anything
2. One logical change per commit
3. State confidence — say whether you KNOW or are GUESSING
4. No bandaids — don't work around broken components, fix them
5. Verify after each change — run `make check`, don't stack unverified changes

## Current git state

- **Branch:** `docs/audit-readme` (current)
- **Also exists:** `ci/harden-workflows` (2 commits ahead of `main`)
  - `877bf93` ci: pin actions to SHAs and harden workflow permissions
  - `fd86a18` docs: fix CI/CD doc drift and document self-hosted runner
- **Uncommitted change in `hal/healthcheck.py`:** Removed `check_containers`
  from the `HEALTH_CHECKS` registry. Root cause: it runs `docker ps` via
  subprocess, but HAL runs inside a Docker container where the binary doesn't
  exist and shouldn't exist (mounting the Docker socket is a security risk).
  Every critical container already has a dedicated HTTP health check.
  This needs to be committed on a proper branch.
- **`.env` change (gitignored, local-only):** Added
  `NTOPNG_URL=http://192.168.5.10:3000` so the container reaches ntopng at
  the host IP instead of defaulting to `localhost:3000` (unreachable from
  inside Docker).
- **Docker image:** Running `ghcr.io/jeanpaul-source/orion:latest` built from
  `main`. Does NOT include the healthcheck fix. CI auto-builds on merge to
  `main`.
- **2 stashes** exist on `main` (unrelated prior work).

## What to do

### Step 1: Commit the healthcheck fix

1. Check `git status` and `git stash list` to understand current state.
2. Create a new branch off `main` named `fix/healthcheck-containers`.
3. Cherry-pick or recreate the `hal/healthcheck.py` change (removing
   `check_containers` from `HEALTH_CHECKS` registry).
4. Run `make check`. Fix anything that breaks.
5. Commit with message: `fix: remove check_containers from health registry`
   and trailer `Co-Authored-By: GitHub Copilot <175728472+Copilot@users.noreply.github.com>`.

### Step 2: Diagnose live system health

1. Check the live system:

   ```bash
   curl -s http://localhost:8087/health/detail \
     -H "Authorization: Bearer $HAL_WEB_TOKEN" | python3 -m json.tool
   ```

2. For every component showing "down" or "degraded": identify the ROOT CAUSE.
   Don't band-aid. Report what you find — we'll fix things in later chats.

### Step 3: Test end-to-end pipeline

1. Test the full pipeline:

   ```bash
   curl -s -X POST http://localhost:8087/chat \
     -H "Authorization: Bearer $HAL_WEB_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"message": "How much disk space is free on the lab?"}' | python3 -m json.tool
   ```

2. Verify intent classification → agent loop → tool calls → LLM response all
   work. Report any failures with root cause analysis.

### Step 4: Open a PR for the healthcheck fix

1. Push the branch and open a PR to `main`.

## Constraints (violating these breaks the system)

- **Ollama is embeddings-only** (`OLLAMA_NUM_GPU=0`) — vLLM owns the GPU
- **Prometheus is port 9091** (NOT 9090 — that's Cockpit)
- **The Judge has no bypass** — every tool call flows through `judge.approve()`
- **`main` is always deployable** — CI builds Docker image on merge
- **Config lives in `hal/config.py`** — never hardcode IPs, ports, paths
- **Commit conventions:** `feat:`, `fix:`, `docs:`, `refactor:`, `test:`,
  `chore:`, `ci:` — max 72 chars, lowercase, no trailing period

## Key commands

```bash
make check        # lint + format + typecheck + test + doc-drift — run before every push
make test         # offline tests only (no Ollama needed)
```
