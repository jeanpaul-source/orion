# Automation & Guardrails — Implementation Plan

> Created: 2026-03-13
> Branch: `docs/automation-guardrails-plan`
> Status: Planning — nothing implemented yet

This document contains the complete validated audit of Orion's automation gaps,
missing guardrails, and documentation inaccuracies — plus GitHub issue bodies,
step-by-step implementation plans, and a sequenced session schedule.

**How to use this document:** Work through the sessions in order. Each session
is self-contained and ends with verification. The AI implementer reads the
relevant section, proposes changes per CLAUDE.md rules (one change at a time,
explain before acting, wait for approval), and you approve or reject.

---

## Table of Contents

- [Validation Summary](#validation-summary)
- [Dependency Map](#dependency-map)
- [Batch 1 — GitHub Settings (F-01, F-12)](#batch-1--github-settings)
- [Batch 2 — Git Config & Local Hooks (F-02, F-03, F-04, F-05, F-18)](#batch-2--git-config--local-hooks)
- [Batch 3 — CD Architecture Fix (F-21)](#batch-3--cd-architecture-fix)
- [Batch 4 — CD Hardening (F-06, F-07, F-08, F-09)](#batch-4--cd-hardening)
- [Batch 5 — Documentation Fixes (F-13, F-14, F-15, F-16, F-17)](#batch-5--documentation-fixes)
- [Batch 6 — Dependencies & Nice-to-haves (F-10, F-11, F-19, F-20)](#batch-6--dependencies--nice-to-haves)
- [Session Schedule](#session-schedule)

---

## Validation Summary

Every finding was cross-checked against the live repo on 2026-03-13. Here is
the status of each:

| Finding | Validated? | Notes |
|---------|-----------|-------|
| F-01 Auto-delete merged branches OFF | **Needs GitHub UI check** | Cannot verify via CLI — requires Settings > General > Pull Requests |
| F-02 Commit-msg hook missing | **Confirmed** | `.git/hooks/` has `pre-commit` and `pre-push` but only `commit-msg.sample` (not an active hook) |
| F-03 fetch.prune not set | **Confirmed** | `git config --get fetch.prune` returns nothing (exit 1) |
| F-04 No push.autoSetupRemote | **Confirmed** | `git config --get push.autoSetupRemote` returns nothing (exit 1) |
| F-05 No pull.rebase | **Confirmed** | `git config --get pull.rebase` returns nothing (exit 1) |
| F-06 No deploy health check | **Confirmed** | `deploy.yml` shows logs but never checks `/health` |
| F-07 No deploy failure notification | **Confirmed** | `deploy.yml` has no `if: failure()` step, no ntfy call |
| F-08 CD never rebuilds | **Confirmed** | `deploy.yml` only checks `^(hal\|harvest)/.*\.py$` — Dockerfile/requirements.txt changes are invisible |
| F-09 No deployed-commit verification | **Confirmed** | `deploy.yml` does `git pull` but never compares HEAD with `github.sha` |
| F-10 CI uses pip install, lock files unused | **Confirmed** | `test.yml` line 28: `pip install -r requirements.txt -r requirements-dev.txt`. Lock files exist (`requirements.lock`, `requirements-dev.lock`) but are unused by CI or Makefile |
| F-11 No Dependabot auto-merge | **Confirmed** | No auto-merge workflow exists in `.github/workflows/` |
| F-12 Strict status checks OFF | **Needs GitHub UI check** | Cannot verify via CLI — requires Settings > Rules inspection |
| F-13 CONTRIBUTING.md claims bypass actor | **Confirmed** | Line 253: "The repository admin bypass actor allows emergency direct pushes" — but ruleset has `bypass_actors: []` |
| F-14 README says Web UI "not yet built" | **Confirmed** | Line 60: "Web UI / Voice interfaces \| Not yet built" — but `hal/static/` has `app.js`, `index.html`, `style.css` |
| F-15 README references SESSION_FINDINGS.md | **Confirmed** | Line 113 links to `SESSION_FINDINGS.md` which does not exist. Actual file: `notes/session-findings-archive.md` |
| F-16 ARCHITECTURE.md says Tempo not deployed | **Confirmed** | Line 244: "Grafana Tempo receiver not yet deployed (planned)" — contradicts OPERATIONS.md which has full Tempo deploy instructions |
| F-17 Hardcoded test counts | **Confirmed** | "1176" appears in README.md (lines 40, 142), CONTRIBUTING.md (lines 81, 99, 215). Current count is exactly 1176, but will drift on next test addition |
| F-18 make install-hooks misses commit-msg | **Confirmed** | Makefile `install-hooks` target (line 39) runs only `pre-commit install --install-hooks --overwrite`. `dev-setup` (line 46) correctly adds `--hook-type commit-msg` |
| F-19 Doc/Makefile/CI install inconsistency | **Confirmed** | CONTRIBUTING.md step-by-step says `pip-sync` with lock files. Makefile `dev-setup` uses `pip install -r`. CI uses `pip install -r`. Three different stories. |
| F-20 No shared VS Code settings.json | **Confirmed** | `.vscode/settings.json` is in `.gitignore` (line 36). Only `launch.json` and `tasks.json` are committed. |
| F-21 Dev workspace = deploy target | **Confirmed** | `deploy.yml` does `cd ~/orion && git pull`. `~/orion` is the dev workspace. 7 remote branches exist — confirms active branching workflow that triggers this bug. |

**Additional observation:** 7 remote branches currently exist on origin:
`chore/lint-hardening-and-docs`, `chore/vram-optimization`,
`dependabot/github_actions/DavidAnson/markdownlint-cli2-action-22`,
`docs/cleanup-scratch-notes`, `feat/test-coverage-push`,
`fix/silent-failures-logging`, `main`. This confirms F-01 (stale branches accumulating).

**Action needed from you before implementation:**

1. Check GitHub UI: Settings > General > Pull Requests — is "Automatically delete head branches" checked? (F-01)
2. Check GitHub UI: Settings > Rules > main-protection — is "Require branches to be up to date before merging" enabled? (F-12)

---

## Dependency Map

```text
F-01 (auto-delete branches)
  └─→ F-03 (fetch.prune — more effective when branches auto-delete)

F-21 (separate deploy directory)  ← P0, do this first among CD changes
  ├─→ F-06 (deploy health check — modifies deploy.yml)
  │     └─→ F-07 (deploy failure notification — needs health check to be meaningful)
  ├─→ F-08 (CD rebuild detection — modifies deploy.yml)
  └─→ F-09 (deployed-commit verification — modifies deploy.yml)

F-10 (lock file decision)
  └─→ F-19 (install method consistency — same decision)

All others: no dependencies, can be done in any order.

```

---

## Batch 1 — GitHub Settings

### Issue: Enable auto-delete of merged branches and strict status checks

**Title:** `chore: enable auto-delete merged branches + strict status checks`

**Labels:** `automation`, `dx`

#### Problem

Two GitHub repo settings are suboptimal:

1. **Auto-delete merged branches is OFF.** After a PR merges, the source branch
   stays on GitHub. Over time stale branches accumulate (currently 6 non-main
   branches on origin). This creates confusion about what's active.

2. **Strict status checks are OFF** (F-12, P3). PRs can merge without re-running
   CI against the latest `main`. Two PRs could each pass CI individually but
   break when combined. Low risk for a solo dev, but free insurance.

#### Evidence

- `git branch -r` shows 7 remote refs including stale feature branches
- Ruleset has `strict_required_status_checks_policy: false` (per audit)

#### Solution

Both are GitHub UI toggles — no code changes needed.

**F-01 — Auto-delete merged branches:**

1. Go to: GitHub repo > Settings > General
2. Scroll to "Pull Requests" section
3. Check "Automatically delete head branches"
4. Click Save

**F-12 — Strict status checks:**

1. Go to: GitHub repo > Settings > Rules > main-protection
2. Edit the ruleset
3. Under "Required status checks", enable "Require branches to be up to date
   before merging"

4. Save

**After both:** Clean up existing stale branches:

```bash
# Delete merged remote branches (run from ~/orion)
git push origin --delete chore/lint-hardening-and-docs
git push origin --delete chore/vram-optimization
git push origin --delete docs/cleanup-scratch-notes
git push origin --delete feat/test-coverage-push
git push origin --delete fix/silent-failures-logging
# Keep dependabot branch — it has an open PR

```

#### Acceptance Criteria

- [ ] New PR → merge → branch auto-deleted on GitHub
- [ ] `git branch -r` shows only `origin/main` and active Dependabot branches
- [ ] PR that's behind `main` shows "Update branch" button before merge is allowed

#### Dependencies

None.

#### Estimated Time

10 minutes (all manual UI clicks).

---

## Batch 2 — Git Config & Local Hooks

### Issue: Fix local git config and install missing commit-msg hook

**Title:** `chore: fix local git config and commit-msg hook installation`

**Labels:** `dx`, `automation`

#### Problem

Five local development issues:

1. **F-02 (P1):** The `commit-msg` hook (which enforces Conventional Commits
   locally via commitlint) is not installed. `.git/hooks/` has `pre-commit` and
   `pre-push` but only `commit-msg.sample`. Bad commit messages pass locally and
   are only caught in CI after push.

2. **F-18 (P1):** `make install-hooks` (the obvious way to reinstall hooks) only
   runs `pre-commit install --install-hooks --overwrite` — this installs
   pre-commit and pre-push hooks but NOT commit-msg. Meanwhile `make dev-setup`
   correctly includes `--hook-type commit-msg`. If someone reinstalls via
   `make install-hooks`, commitlint is silently lost.

3. **F-03 (P1):** `fetch.prune` is not set. Local `remotes/origin/` references
   to deleted branches persist forever. `git branch -a` shows branches that no
   longer exist on GitHub.

4. **F-04 (P2):** `push.autoSetupRemote` is not set. First push of a new branch
   requires `--set-upstream origin <branch>` — confusing error for a new dev.

5. **F-05 (P2):** `pull.rebase` is not set. `git pull` with local commits
   creates merge commits instead of replaying local commits on top.

#### Evidence

```bash
# F-02: No commit-msg hook (only .sample)
$ ls .git/hooks/ | grep commit-msg
commit-msg.sample

# F-18: install-hooks target is incomplete
$ grep -A2 'install-hooks:' Makefile
install-hooks:
    .venv/bin/pre-commit install --install-hooks --overwrite
# Compare with dev-setup which has the extra line:
#   .venv/bin/pre-commit install --hook-type commit-msg

# F-03, F-04, F-05: All unset
$ git config --get fetch.prune     # exit 1
$ git config --get push.autoSetupRemote  # exit 1
$ git config --get pull.rebase     # exit 1

```

#### Solution

**Step 1 — Fix Makefile `install-hooks` target (F-18):**

File: `Makefile`, line 39-40

Change:

```makefile
install-hooks:
    .venv/bin/pre-commit install --install-hooks --overwrite

```

To:

```makefile
install-hooks:
    .venv/bin/pre-commit install --install-hooks --overwrite
    .venv/bin/pre-commit install --hook-type commit-msg

```

This makes `install-hooks` match `dev-setup` behavior.

**Step 2 — Install the commit-msg hook now (F-02):**

```bash
.venv/bin/pre-commit install --hook-type commit-msg

```

Verify:

```bash
ls -la .git/hooks/commit-msg
# Should show a real file, not .sample

```

**Step 3 — Set git config (F-03, F-04, F-05):**

```bash
git config --global fetch.prune true
git config --global push.autoSetupRemote true
git config --global pull.rebase true

```

These are `--global` (user-level) settings because they're developer preferences
that apply to all repos, not project-specific config.

**Step 4 — Clean up stale local refs:**

```bash
git fetch --prune
git branch -a  # Should only show active remote branches

```

#### Acceptance Criteria

- [ ] `ls .git/hooks/commit-msg` shows a real file (not `.sample`)
- [ ] `echo "bad message" | npx commitlint` rejects the message
- [ ] `git commit -m "bad message" --allow-empty` is rejected by the hook
- [ ] `make install-hooks` installs all three hook types (verify with `ls .git/hooks/`)
- [ ] `git config --get fetch.prune` returns `true`
- [ ] `git config --get push.autoSetupRemote` returns `true`
- [ ] `git config --get pull.rebase` returns `true`
- [ ] `git branch -a` shows no stale remote refs

#### Dependencies

F-01 should be done first (auto-delete makes prune more effective), but is not
a hard blocker.

#### What Could Go Wrong

- `pull.rebase = true` changes pull behavior. If you're mid-merge on another
  branch, finish that first. For any repo where you explicitly want merge
  commits, use `git pull --no-rebase` as an override.

- Installing the commit-msg hook means ALL future commits must follow
  Conventional Commits format. This is already enforced in CI, so nothing new
  — just caught earlier.

#### Estimated Time

15 minutes (one Makefile edit + terminal commands).

---

## Batch 3 — CD Architecture Fix

### Issue: Separate dev workspace from deploy target

**Title:** `fix: separate deploy clone from dev workspace`

**Labels:** `ci-cd`, `guardrails`

#### Problem

`deploy.yml` does `cd ~/orion && git pull`. `~/orion` is also the dev workspace.
When a PR merges while the dev workspace is on a feature branch, `git pull` fails
with: *"Your configuration specifies to merge with the ref 'refs/heads/\<branch\>'
from the remote, but no such ref was fetched."*

This is **P0** — it breaks every deploy that happens while you're on a feature
branch, which is the normal workflow. The container continues running old code
until you manually intervene.

#### Evidence

- `deploy.yml` step 3: `cd ~/orion && git pull`
- 7 remote branches exist — confirms active feature branch workflow
- This failure already occurred on PR #28

#### Solution

Create a dedicated `~/orion-deploy` directory that always stays on `main`.
The dev workspace (`~/orion`) remains untouched.

**Step 1 — Clone the deploy copy:**

```bash
# On the-lab as user jp
git clone https://github.com/jeanpaul-source/orion ~/orion-deploy
cd ~/orion-deploy
git checkout main

```

**Step 2 — Copy secrets:**

```bash
cp ~/orion/.env ~/orion-deploy/.env

```

**Step 3 — Update docker-compose.yml bind mounts:**

File: `docker-compose.yml`

Change the three `~/orion` volume mounts to `~/orion-deploy`:

```yaml
    volumes:
      # HAL's state — the ONLY read-write mount

      - /home/jp/.orion:/home/hal/.orion:rw

      # Codebase — read-only (LLM cannot modify its own code)

      - /home/jp/orion-deploy:/app:ro

      # Config (secrets) — read-only single file

      - /home/jp/orion-deploy/.env:/app/.env:ro

```

Note: Only the `/app:ro` and `.env:ro` mounts change. The `.orion` state mount
stays as-is (it's the state directory, not the codebase).

**Step 4 — Update deploy.yml:**

File: `.github/workflows/deploy.yml`

Replace the "Pull latest code" step:

```yaml

      - name: Pull latest code
        run: |
          cd ~/orion-deploy
          git checkout main
          git pull origin main

```

Replace the "Restart container" step's `cd` target:

```yaml

      - name: Restart container
        if: steps.changed.outputs.python == 'true'
        run: |
          cd ~/orion-deploy
          docker compose restart

```

Replace the "Show container logs" step (no `cd` needed — `docker logs` doesn't
depend on cwd, but add for clarity if desired).

**Step 5 — Update shell aliases in `~/.bashrc`:**

```bash
# Find and update these aliases:
alias orion-update="cd ~/orion-deploy && git pull origin main && echo done"
alias orion-deploy="cd ~/orion-deploy && git pull origin main && docker compose build && docker compose up -d"
# The 'hal' alias stays the same — container name 'orion' doesn't change

```

**Step 6 — Migrate the running container:**

```bash
# Stop container from dev workspace
cd ~/orion
docker compose down

# Start from deploy workspace
cd ~/orion-deploy
docker compose up -d

# Verify
docker ps | grep orion
curl http://localhost:8087/health

```

**Step 7 — Update OPERATIONS.md:**

Add a section explaining the dev vs. deploy split:

> **Two directories, two purposes:**
>
> | Directory | Purpose | Branch |
> |-----------|---------|--------|
> | `~/orion` | Dev workspace (VS Code) | Any feature branch |
> | `~/orion-deploy` | Deploy target (CD pipeline) | Always `main` |
>
> The CD pipeline (`deploy.yml`) pulls into `~/orion-deploy`. The Docker
> container bind-mounts `~/orion-deploy:/app:ro`. Your dev workspace at
> `~/orion` is never touched by the deploy process.

Update the "Deploy" section in CONTRIBUTING.md similarly.

#### Acceptance Criteria

- [ ] `~/orion-deploy` exists and is on `main`
- [ ] `~/orion-deploy/.env` exists with correct secrets
- [ ] `docker inspect orion` shows `/home/jp/orion-deploy:/app:ro` bind mount
- [ ] `curl http://localhost:8087/health` returns 200
- [ ] Switch dev workspace to a feature branch: `cd ~/orion && git checkout -b test-deploy`
- [ ] Trigger a deploy (merge a trivial PR) — deploy succeeds
- [ ] Container serves new code (verify via git SHA or a test endpoint)
- [ ] `deploy.yml` references `~/orion-deploy`, not `~/orion`
- [ ] OPERATIONS.md documents the two-directory setup
- [ ] CONTRIBUTING.md deploy section updated

#### What Could Go Wrong

- **Container downtime during migration** — the `docker compose down` → `up -d`
  transition takes ~30 seconds. The 120s `start_period` means the container may
  take up to 2 minutes to report healthy. Plan for 2-3 minutes of downtime.

- **Forgotten .env sync** — if `.env` changes in the future, it must be copied
  to both locations. Consider symlinking: `ln -sf ~/orion/.env ~/orion-deploy/.env`
  (but note: the dev workspace `.env` must stay correct for this to work).

- **Rollback:** If something goes wrong, reverse the migration:

  ```bash
  cd ~/orion-deploy && docker compose down
  cd ~/orion && git checkout main
  # Revert docker-compose.yml to use /home/jp/orion
  docker compose up -d

  ```

#### Dependencies

None — but this must be done BEFORE Batch 4 (all deploy.yml changes).

#### Estimated Time

45-60 minutes (code changes + live migration + verification).

---

## Batch 4 — CD Hardening

### Issue: Add health check, failure notification, rebuild detection, and SHA verification to deploy pipeline

**Title:** `fix: harden CD pipeline — health check, notifications, rebuild, SHA verify`

**Labels:** `ci-cd`, `guardrails`

#### Problem

Four gaps in `deploy.yml`:

1. **F-06 (P1):** Deploy "succeeds" (green workflow) even if the container is
   crash-looping. The container has a healthcheck (`curl /health`) but deploy.yml
   never checks it.

2. **F-07 (P2):** Failed deploys are only visible in the GitHub Actions UI. No
   push notification. A broken deploy can sit unnoticed for hours.

3. **F-08 (P2):** The pipeline only detects Python file changes and runs
   `docker compose restart`. Changes to `Dockerfile`, `requirements.txt`,
   `docker-compose.yml`, or `ops/supervisord.conf` need a full `docker compose
   build && docker compose up -d` but the pipeline never does this. Adding a
   pip dependency and merging leaves the container with old packages.

4. **F-09 (P1):** After `git pull`, deploy.yml never verifies that HEAD matches
   the expected commit. If pull fails silently or leaves the repo in a bad
   state, the deploy proceeds with old code.

#### Evidence

```yaml
# deploy.yml — current state
# Step 3: git pull with no verification
# Step 4: docker compose restart (never build)
# Step 5: docker logs (no health check)
# No failure notification step exists

```

#### Solution

Complete rewrite of `deploy.yml`. This goes on top of the F-21 changes (which
moved the target to `~/orion-deploy`).

New `deploy.yml`:

```yaml
name: Deploy to the-lab

on:
  push:
    branches: [main]

jobs:
  deploy:
    name: Deploy to the-lab
    runs-on: self-hosted

    steps:

      - name: Checkout repository
        uses: actions/checkout@v6
        with:
          fetch-depth: 2

      # Detect what changed to decide: restart vs. rebuild vs. skip

      - name: Detect changed files
        id: changed
        run: |
          # Python files → at minimum a restart
          if git diff --name-only HEAD^ HEAD | grep -qE '^(hal|harvest)/.*\.py$'; then
            echo "python=true" >> "$GITHUB_OUTPUT"
          else
            echo "python=false" >> "$GITHUB_OUTPUT"
          fi

          # Infrastructure files → full rebuild required
          if git diff --name-only HEAD^ HEAD | grep -qE '^(Dockerfile|requirements\.txt|docker-compose\.yml|ops/supervisord\.conf)$'; then
            echo "infra=true" >> "$GITHUB_OUTPUT"
          else
            echo "infra=false" >> "$GITHUB_OUTPUT"
          fi

      # Pull latest code into the deploy directory

      - name: Pull latest code
        run: |
          cd ~/orion-deploy
          git checkout main
          git pull origin main

      # Verify the deploy directory has the correct commit

      - name: Verify deployed commit
        run: |
          DEPLOYED_SHA=$(cd ~/orion-deploy && git rev-parse HEAD)
          EXPECTED_SHA="${{ github.sha }}"
          echo "Deployed: $DEPLOYED_SHA"
          echo "Expected: $EXPECTED_SHA"
          if [ "$DEPLOYED_SHA" != "$EXPECTED_SHA" ]; then
            echo "::error::Commit mismatch — deploy directory has wrong code"
            exit 1
          fi

      # Full rebuild if infrastructure files changed

      - name: Rebuild container
        if: steps.changed.outputs.infra == 'true'
        run: |
          cd ~/orion-deploy
          docker compose build
          docker compose up -d

      # Restart only if Python files changed (but no infra changes)

      - name: Restart container
        if: steps.changed.outputs.python == 'true' && steps.changed.outputs.infra == 'false'
        run: |
          cd ~/orion-deploy
          docker compose restart

      # Wait for container to be healthy
      # The container has start_period: 120s, so we allow up to 150s

      - name: Wait for healthy container
        if: steps.changed.outputs.python == 'true' || steps.changed.outputs.infra == 'true'
        run: |
          echo "Waiting for container to become healthy..."
          for i in $(seq 1 30); do
            STATUS=$(docker inspect --format='{{.State.Health.Status}}' orion 2>/dev/null || echo "unknown")
            echo "  Attempt $i/30: $STATUS"
            if [ "$STATUS" = "healthy" ]; then
              echo "Container is healthy"
              exit 0
            fi
            sleep 5
          done
          echo "::error::Container did not become healthy within 150 seconds"
          docker logs --tail 50 orion
          exit 1

      # Always show logs for debugging

      - name: Show container logs
        if: always()
        run: docker logs --tail 20 orion

      # Notify on failure via ntfy

      - name: Notify on failure
        if: failure()
        run: |
          curl -s \
            -H "Title: Orion deploy failed" \
            -H "Priority: high" \
            -H "Tags: rotating_light" \
            -d "Deploy of ${{ github.sha }} failed. Check: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}" \
            "${{ secrets.NTFY_URL }}" || true

```

**GitHub Secret needed:** Add `NTFY_URL` as a repository secret:

1. GitHub repo > Settings > Secrets and variables > Actions
2. New repository secret: `NTFY_URL` = the ntfy topic URL (same value as in `.env`)

#### Acceptance Criteria

- [ ] Deploy with Python-only changes → `docker compose restart` → health check passes → green
- [ ] Deploy with Dockerfile change → `docker compose build && up -d` → health check passes → green
- [ ] Deploy with docs-only change → no restart, no build → green
- [ ] Intentionally break the container (e.g., bad import) → health check fails → workflow red → ntfy notification received
- [ ] Commit SHA mismatch (simulated) → workflow fails at verify step
- [ ] `NTFY_URL` secret exists in GitHub repo settings

#### What Could Go Wrong

- **Health check timeout:** The 150-second timeout (30 attempts × 5 seconds)
  should cover the 120s `start_period`, but if the container is slow to start
  (e.g., after a rebuild), you may need to increase the attempts.

- **ntfy URL missing:** The `|| true` at the end of the curl prevents the
  notification step from failing the workflow if ntfy is unreachable.

- **Rebuild takes too long:** `docker compose build` downloads packages. On a
  slow connection this could take minutes. The self-hosted runner has no
  timeout by default, so this is safe but slow.

#### Dependencies

**F-21 (Batch 3) must be done first.** All `cd` paths reference `~/orion-deploy`.

#### Estimated Time

30-45 minutes (deploy.yml rewrite + adding GitHub secret + testing).

---

## Batch 5 — Documentation Fixes

### Issue: Fix documentation inaccuracies across README, CONTRIBUTING, and ARCHITECTURE

**Title:** `docs: fix 5 documentation inaccuracies`

**Labels:** `docs`

#### Problem

Five documentation inaccuracies that mislead developers or break links:

1. **F-13 (P1):** CONTRIBUTING.md line 253 claims "The repository admin bypass
   actor allows emergency direct pushes" — but `bypass_actors: []` in the
   ruleset. Nobody can bypass.

2. **F-14 (P1):** README.md line 60: "Web UI / Voice interfaces | Not yet
   built" — but `hal/static/` has a working chat UI (`app.js`, `index.html`,
   `style.css`) served by FastAPI.

3. **F-15 (P1):** README.md line 113 links to `SESSION_FINDINGS.md` which does
   not exist. The actual file is `notes/session-findings-archive.md`.

4. **F-16 (P1):** ARCHITECTURE.md line 244: "Grafana Tempo receiver not yet
   deployed (planned)" — contradicts OPERATIONS.md which has full Tempo deploy
   and verification instructions, and memory/SUMMARY.md which lists Tempo as
   current architecture.

5. **F-17 (P3):** "1176" is hardcoded in README.md (lines 40, 142) and
   CONTRIBUTING.md (lines 81, 95, 99, 215). This count drifts every time tests
   are added. Currently accurate (1176 collected) but will be wrong soon.

#### Evidence

```bash
# F-13:
$ grep -n 'bypass' CONTRIBUTING.md
253: ...bypass actor allows emergency direct pushes...

# F-14:
$ ls hal/static/
app.js  index.html  style.css

# F-15:
$ ls SESSION_FINDINGS.md
ls: cannot access 'SESSION_FINDINGS.md': No such file or directory
$ ls notes/session-findings-archive.md
notes/session-findings-archive.md  # exists

# F-16:
$ grep -n 'not yet deployed' ARCHITECTURE.md
244:- Grafana Tempo receiver not yet deployed (planned)

# F-17:
$ pytest tests/ --ignore=tests/test_intent.py --co -q | tail -1
1176 tests collected in 0.38s

```

#### Solution

**F-13 — Fix bypass actor claim in CONTRIBUTING.md:**

File: `CONTRIBUTING.md`, around line 253

Change:

```markdown
`main` is blocked by ruleset. The repository admin bypass actor allows emergency
direct pushes when genuinely needed.

```

To:

```markdown
`main` is blocked by ruleset with no bypass actors. In a genuine emergency,
temporarily disable the ruleset in GitHub Settings > Rules, push directly,
then re-enable the ruleset immediately.

```

**F-14 — Fix Web UI status in README.md:**

File: `README.md`, line 60

Change:

```markdown
| Web UI / Voice interfaces | Not yet built |

```

To:

```markdown
| Web UI (browser chat) | Working |
| Voice interfaces | Not yet built |

```

Also add `hal/static/` to the Key Files table:

```markdown
| `hal/static/` | Web UI — vanilla JS chat interface served by FastAPI at `/` |

```

**F-15 — Fix broken SESSION_FINDINGS.md link in README.md:**

File: `README.md`, line 113

Change:

```markdown
| [SESSION_FINDINGS.md](SESSION_FINDINGS.md) | Ground-truth audit of what runs vs. what is documented |

```

To:

```markdown
| [notes/session-findings-archive.md](notes/session-findings-archive.md) | Session findings archive — ground-truth audits |

```

**F-16 — Fix Tempo status in ARCHITECTURE.md:**

File: `ARCHITECTURE.md`, line 244

Change:

```markdown

- Grafana Tempo receiver not yet deployed (planned)

```

To:

```markdown

- OpenTelemetry traces exported to Grafana Tempo via OTLP HTTP (port 4318). See [OPERATIONS.md](OPERATIONS.md) for deploy and verification steps.

```

**F-17 — Replace hardcoded test counts:**

Across README.md and CONTRIBUTING.md, replace exact counts with approximate
language. The exact count lives in CI output (pytest prints it every run).

README.md line 40:

```markdown
# Before:
1176 offline tests (35 intent classifier tests additionally require Ollama).

# After:
~1200 offline tests (35+ intent classifier tests additionally require Ollama).

```

README.md line 142:

```markdown
# Before:
| `tests/` | 1176 offline tests + 35 intent classifier tests (require Ollama) |

# After:
| `tests/` | Offline test suite + intent classifier tests (require Ollama) |

```

CONTRIBUTING.md line 81:

```markdown
# Before:
make test           # offline tests only (no Ollama needed) — 1176 tests

# After:
make test           # offline tests only (no Ollama needed)

```

CONTRIBUTING.md lines 95-99:

```markdown
# Before:
1211 tests total:

- **35 intent classifier tests** — ...
- **1176 offline tests** — ...

# After:
Two test sets:

- **~35 intent classifier tests** — ...
- **~1200 offline tests** — ...

```

CONTRIBUTING.md line 215:

```markdown
# Before:

- `make test` passes (all 1176 offline tests)

# After:

- `make test` passes (all offline tests)

```

#### Acceptance Criteria

- [ ] `make doc-drift` passes (the doc-drift checker validates these files)
- [ ] README.md: Web UI shown as "Working", Voice as "Not yet built"
- [ ] README.md: SESSION_FINDINGS link points to `notes/session-findings-archive.md`
- [ ] README.md: No hardcoded test count numbers
- [ ] ARCHITECTURE.md: Tempo described as deployed
- [ ] CONTRIBUTING.md: No bypass actor claim
- [ ] CONTRIBUTING.md: No hardcoded test count numbers
- [ ] `make check` passes

#### What Could Go Wrong

- **doc-drift checker** may need updating if it validates specific test count
  numbers. Check `scripts/check_doc_drift.py` for any hardcoded count assertions
  before making changes. (The audit notes F-17 says the checker uses ±40%
  tolerance, so approximate language should pass.)

- These are all safe text changes. Rollback: `git checkout -- <file>`.

#### Dependencies

None.

#### Estimated Time

20-30 minutes (text edits across 3 files + verification).

---

## Batch 6 — Dependencies & Nice-to-haves

### Issue A: Decide on lock files and fix install consistency

**Title:** `chore: resolve lock file usage — use everywhere or remove`

**Labels:** `ci-cd`, `dx`

#### Problem (F-10 + F-19)

Three different install methods exist:

| Context | Method | Source |
|---------|--------|--------|
| CI (`test.yml`) | `pip install -r requirements.txt` | Plain files |
| Makefile (`dev-setup`) | `pip install -r requirements.txt` | Plain files |
| CONTRIBUTING.md step-by-step | `pip-sync requirements.lock` | Lock files with hashes |

Lock files exist (`requirements.lock`, `requirements-dev.lock`) with hashes, but
nothing enforces them. CI and Makefile ignore them. Different environments could
get different package versions.

#### Solution — Recommended: Option A (use lock files everywhere)

Lock files with hashes protect against tampered packages and ensure reproducible
installs. The lock files already exist — they just aren't used.

**Step 1 — Update CI (`test.yml`):**

```yaml

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip pip-tools
          pip-sync requirements.lock requirements-dev.lock

```

**Step 2 — Update Makefile `dev-setup`:**

```makefile
dev-setup:
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip pip-tools
    .venv/bin/pip-sync requirements.lock requirements-dev.lock
    npm install
    .venv/bin/pre-commit install --install-hooks --overwrite
    .venv/bin/pre-commit install --hook-type commit-msg
    @echo ""
    @echo "Dev environment ready. Hooks installed."
    @echo "  Run 'make check' to verify everything passes."

```

**Step 3 — Add a Makefile target to recompile locks:**

```makefile
lock: ## Recompile lock files from requirements.txt
    .venv/bin/pip-compile requirements.txt --generate-hashes --allow-unsafe -o requirements.lock
    .venv/bin/pip-compile requirements-dev.txt --generate-hashes --allow-unsafe -o requirements-dev.lock

```

**Step 4 — Update CONTRIBUTING.md:**

Make the quick-start and step-by-step sections consistent. Both should reference
`make dev-setup` as the primary path. The step-by-step should use `pip-sync`
with lock files (which it already does — no change needed there).

**Step 5 — Update OPERATIONS.md host venv setup:**

```bash
python -m venv .venv && source .venv/bin/activate
pip install pip-tools
pip-sync requirements.lock

```

#### Acceptance Criteria

- [ ] CI installs from lock files
- [ ] `make dev-setup` installs from lock files
- [ ] `make lock` recompiles lock files
- [ ] CONTRIBUTING.md, OPERATIONS.md, Makefile, and CI all agree on the method
- [ ] `make check` passes after a clean `make dev-setup`

#### Dependencies

None (but informs F-19 which is the same decision).

#### Estimated Time

30 minutes.

---

### Issue B: Add Dependabot auto-merge for non-major updates

**Title:** `ci: add Dependabot auto-merge workflow`

**Labels:** `automation`, `ci-cd`

#### Problem (F-11)

Dependabot creates PRs for outdated dependencies, but they require manual merge
even when CI passes. For a solo developer, this means security patches pile up
waiting for attention.

#### Solution

Create `.github/workflows/dependabot-automerge.yml`:

```yaml
name: Dependabot auto-merge

on:
  pull_request:

permissions:
  contents: write
  pull-requests: write

jobs:
  auto-merge:
    runs-on: ubuntu-latest
    if: github.actor == 'dependabot[bot]'

    steps:

      - name: Fetch Dependabot metadata
        id: metadata
        uses: dependabot/fetch-metadata@v2
        with:
          github-token: "${{ secrets.GITHUB_TOKEN }}"

      - name: Auto-merge non-major updates
        if: steps.metadata.outputs.update-type != 'version-update:semver-major'
        run: gh pr merge --auto --squash "$PR_URL"
        env:
          PR_URL: ${{ github.event.pull_request.html_url }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

```

This auto-merges patch and minor version updates after CI passes. Major version
bumps still require manual review.

#### Acceptance Criteria

- [ ] Workflow file exists at `.github/workflows/dependabot-automerge.yml`
- [ ] Next Dependabot PR (patch or minor) auto-merges after CI passes
- [ ] Major version Dependabot PR does NOT auto-merge

#### Dependencies

None.

#### Estimated Time

10 minutes.

---

### Issue C: Add shared VS Code settings.json

**Title:** `dx: add shared VS Code settings.json`

**Labels:** `dx`

#### Problem (F-20)

`.vscode/settings.json` is in `.gitignore`. The project has `launch.json` and
`tasks.json` committed, but no shared editor settings. This means:

- Python interpreter path may point to wrong venv
- Ruff may not be configured as the formatter/linter in the editor
- Format-on-save may not work or may use the wrong formatter
- Editor squiggles may not match CI

#### Solution

**Step 1 — Remove from .gitignore:**

File: `.gitignore`, line 36

Remove:

```text
.vscode/settings.json
```

**Step 2 — Create `.vscode/settings.json`:**

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "[python]": {
    "editor.formatOnSave": true,
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.codeActionsOnSave": {
      "source.fixAll.ruff": "explicit",
      "source.organizeImports.ruff": "explicit"
    }
  },
  "[markdown]": {
    "editor.formatOnSave": false
  },
  "python.analysis.typeCheckingMode": "basic",
  "files.trimTrailingWhitespace": true,
  "files.insertFinalNewline": true
}

```

#### Acceptance Criteria

- [ ] `.vscode/settings.json` is tracked by git
- [ ] Opening the project in VS Code shows correct Python interpreter
- [ ] Saving a Python file auto-formats with Ruff
- [ ] No editor squiggles that don't also fail in CI

#### Dependencies

None.

#### Estimated Time

10 minutes.

---

## Session Schedule

Each session is designed to be completable in one sitting, self-contained (no
half-done states), and ordered by dependency chain.

### Session 1 — GitHub Settings + Git Config (~30 min)

**What:** Batch 1 + Batch 2

1. **You (GitHub UI):** Enable auto-delete merged branches (F-01)
2. **You (GitHub UI):** Enable strict status checks (F-12)
3. **Terminal:** Delete stale remote branches
4. **AI + you:** Fix Makefile `install-hooks` target (F-18)
5. **Terminal:** Install commit-msg hook (F-02)
6. **Terminal:** Set git config (F-03, F-04, F-05)
7. **Terminal:** `git fetch --prune`
8. **Verify:** `make check` passes
9. **Commit + push + PR**

**Ends with:** All local dev tooling working correctly. Commit messages enforced
locally. Git config optimized. Stale branches cleaned up.

---

### Session 2 — Separate Deploy Directory (~60 min)

**What:** Batch 3 (F-21)

1. **Terminal:** Clone `~/orion-deploy`
2. **Terminal:** Copy `.env`
3. **AI + you:** Edit `docker-compose.yml` (change bind mounts)
4. **AI + you:** Edit `deploy.yml` (change `cd` targets)
5. **Terminal:** Update `~/.bashrc` aliases
6. **Terminal:** Migrate container (`docker compose down` → `up -d`)
7. **Verify:** `curl http://localhost:8087/health` returns 200
8. **AI + you:** Update OPERATIONS.md and CONTRIBUTING.md
9. **Verify:** `make check` passes
10. **Commit + push + PR**

**Ends with:** Deploy pipeline targets `~/orion-deploy`. Dev workspace is
independent. Container running from new location.

**Risk window:** ~2-3 minutes of container downtime during migration (step 6).
Do this when you're not actively using HAL.

---

### Session 3 — CD Hardening (~45 min)

**What:** Batch 4 (F-06, F-07, F-08, F-09)

**Prerequisite:** Session 2 merged to `main`.

1. **You (GitHub UI):** Add `NTFY_URL` as a repository secret
2. **AI + you:** Rewrite `deploy.yml` with all four improvements
3. **Verify:** `make check` passes
4. **Commit + push + PR**
5. **After merge:** Observe the deploy — it should health-check and pass
6. **Test failure notification:** Temporarily break something, push, verify
   ntfy alert arrives (then revert)

**Ends with:** Deploy pipeline verifies commits, detects rebuild needs, health
checks the container, and notifies on failure.

---

### Session 4 — Documentation Fixes (~30 min)

**What:** Batch 5 (F-13, F-14, F-15, F-16, F-17)

1. **AI + you:** Fix CONTRIBUTING.md bypass claim (F-13)
2. **AI + you:** Fix README.md Web UI status (F-14)
3. **AI + you:** Fix README.md SESSION_FINDINGS link (F-15)
4. **AI + you:** Fix ARCHITECTURE.md Tempo status (F-16)
5. **AI + you:** Replace hardcoded test counts (F-17)
6. **Verify:** `make doc-drift` passes
7. **Verify:** `make check` passes
8. **Commit + push + PR**

**Ends with:** All documentation matches reality. No broken links. No stale
status claims. Test counts won't drift.

---

### Session 5 — Dependencies & Polish (~45 min)

**What:** Batch 6 (F-10, F-19, F-11, F-20)

1. **AI + you:** Switch CI and Makefile to lock files (F-10, F-19)
2. **AI + you:** Add `make lock` target
3. **AI + you:** Update CONTRIBUTING.md and OPERATIONS.md install instructions
4. **AI + you:** Create Dependabot auto-merge workflow (F-11)
5. **AI + you:** Create `.vscode/settings.json` and remove from `.gitignore` (F-20)
6. **Verify:** `make dev-setup` works from scratch (test in a temp dir if possible)
7. **Verify:** `make check` passes
8. **Commit + push + PR**

**Ends with:** Consistent install method everywhere. Dependabot auto-merges
non-major bumps. VS Code settings shared.

---

### Total Estimated Time

| Session | Time | Priority |
|---------|------|----------|
| Session 1 — GitHub + Git Config | ~30 min | P1 |
| Session 2 — Deploy Directory | ~60 min | P0 |
| Session 3 — CD Hardening | ~45 min | P1 |
| Session 4 — Documentation | ~30 min | P1 |
| Session 5 — Dependencies & Polish | ~45 min | P2-P3 |
| **Total** | **~3.5 hours** | |

Sessions 1 and 2 are the highest priority. Session 2 unblocks Session 3.
Sessions 4 and 5 can be done in any order after Session 2.

---

## Glossary

Terms used in this document that may be unfamiliar:

- **CD (Continuous Deployment):** Automated process that deploys code to the
  server after it passes tests. Orion's CD is `deploy.yml`.

- **CI (Continuous Integration):** Automated testing that runs on every push.
  Orion's CI is `test.yml`.

- **Conventional Commits:** A commit message format like `feat: add feature`
  or `fix: repair bug`. Enforced by commitlint.

- **Dependabot:** GitHub's automated dependency updater. Creates PRs when
  packages have new versions.

- **fetch.prune:** Git setting that auto-removes local references to branches
  that have been deleted on the remote (GitHub).

- **Lock file:** A file listing exact package versions + hashes. Ensures
  everyone installs identical packages. Like a recipe with exact measurements
  vs. "some flour."

- **ntfy:** A push notification service. Orion uses it for alerts.
- **pip-sync:** A tool that installs exactly what's in a lock file — nothing
  more, nothing less. Stricter than `pip install`.

- **pip-compile:** A tool that reads `requirements.txt` (loose versions) and
  produces a lock file (exact versions + hashes).

- **pre-commit hook:** A script that runs automatically before `git commit`.
  Catches errors before they enter history.

- **pull.rebase:** Git setting that replays your local commits on top of remote
  changes instead of creating a merge commit.

- **push.autoSetupRemote:** Git setting that auto-configures tracking when you
  push a new branch. Avoids the `--set-upstream` error.

- **Ruleset:** GitHub branch protection rules. Orion's `main-protection`
  ruleset requires CI to pass before merging.

- **Self-hosted runner:** A GitHub Actions runner that runs on YOUR server
  instead of GitHub's cloud. Orion uses this for deployments.

- **SHA:** A unique identifier (hash) for each git commit. Looks like
  `a1b2c3d4...`. Used to verify the correct code is deployed.

- **start_period:** Docker healthcheck setting — how long to wait before
  checking health. Gives the container time to start up.
