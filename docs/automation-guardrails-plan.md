# Automation & Guardrails — Implementation Plan

> Created: 2026-03-13
> Branch: `docs/automation-guardrails-plan`
> Status: All 5 sessions complete. Final PR: #38 (`chore/dependency-consistency`).

This document contains the complete validated audit of Orion's automation gaps,
missing guardrails, and documentation inaccuracies — plus GitHub issue bodies,
step-by-step implementation plans, and a sequenced session schedule.

**How to use this document:** Work through the sessions in order. Each session
is self-contained and ends with verification. The AI implementer reads the
relevant section, makes changes which you review as diffs in the editor. Each
finding gets its own commit.

---

## Table of Contents

- [Validation Summary](#validation-summary)
- [Dependency Map](#dependency-map)
- [Batch 1 — GitHub Settings (F-01, F-12)](#batch-1--github-settings)
- [Batch 2 — Git Config & Local Hooks (F-02, F-03, F-04, F-05, F-18)](#batch-2--git-config--local-hooks)
- [Batch 3 — Image-Based Deploy (F-21, F-08, F-09)](#batch-3--image-based-deploy)
- [Batch 4 — CD Hardening (F-06, F-07)](#batch-4--cd-hardening)
- [Batch 5 — Documentation Fixes (F-13, F-14, F-15, F-16, F-17, F-22)](#batch-5--documentation-fixes)
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
| F-22 CLAUDE.md assumes Claude Code, not Copilot | **Confirmed** | CLAUDE.md's stop-and-wait proposal format, one-change-per-commit cycle, and plan doc intro all assume Claude Code terminal sessions. In VS Code Copilot, these rules fight the tool — the user reviews diffs directly in the editor, not proposal blocks. |

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

F-21 (image-based deploy)  ← P0, do this first among CD changes
  ├─→ F-06 (deploy health check — modifies deploy.yml)
  │     └─→ F-07 (deploy failure notification — needs health check to be meaningful)
  ├── F-08 (CD rebuild detection — solved by image build; every merge builds a fresh image)
  └── F-09 (deployed-commit verification — solved by image tag = git SHA)

F-10 (lock file decision)
  └─→ F-19 (install method consistency — same decision)

F-22 (CLAUDE.md workflow update)
  └─→ No dependencies, but doing this early makes all other sessions smoother
      since it removes instructions that fight the VS Code Copilot workflow.

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

## Batch 3 — Image-Based Deploy

### Issue: Switch to image-based deploys — eliminate git-pull-on-server pattern

**Title:** `fix: image-based deploy via GHCR — remove source bind mount`

**Labels:** `ci-cd`, `guardrails`

#### Problem

Two related bugs with the current deploy model:

1. **F-21 (P0):** `deploy.yml` does `cd ~/orion && git pull`. `~/orion` is the
   dev workspace. When you're on a feature branch, `git pull` fails. This broke
   deploy on PR #28.

2. **The bind mount problem:** `docker-compose.yml` mounts
   `/home/jp/orion:/app:ro`. This means the production container runs whatever
   code is in the dev workspace — including half-finished feature branches.

The `git pull` failure is a symptom. The root cause is that the deploy model
couples the production container to the local filesystem state.

#### Evidence

- `deploy.yml` step 3: `cd ~/orion && git pull`
- `docker-compose.yml`: `/home/jp/orion:/app:ro` bind mount
- 7 remote branches exist — confirms active feature branch workflow
- Already broke on PR #28

#### Solution — Image-based deploy via GHCR

Instead of bind-mounting source code, **bake it into the Docker image** and
publish to GitHub Container Registry (GHCR). The Dockerfile already does
`COPY . .` — it's just overridden by the bind mount at runtime.

This eliminates:

- `git pull` on the server (no local clone needed for deploys)
- Source code bind mount (code is inside the image)
- Dev/deploy coupling (image is built from `main`, not the local workspace)
- F-08 (rebuild detection) — every merge builds a fresh image automatically
- F-09 (SHA verification) — the image tag IS the git SHA

**Step 1 — Create CI build workflow (`.github/workflows/build.yml`):**

```yaml
name: Build and push image

on:
  push:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build:
    name: Build and push
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - name: Checkout
        uses: actions/checkout@v6

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: |
            ghcr.io/${{ github.repository }}:latest
            ghcr.io/${{ github.repository }}:${{ github.sha }}
```

Every push to `main` builds and pushes two tags: `latest` (for convenience)
and the full SHA (for rollback and verification).

**Step 2 — Update `docker-compose.yml`:**

Remove the source code bind mount and point `image:` at GHCR:

```yaml
services:
  hal:
    image: ghcr.io/jeanpaul-source/orion:latest
    container_name: orion
    restart: unless-stopped
    # ... (security_opt, extra_hosts, ports unchanged)

    volumes:
      # HAL's state — the ONLY read-write mount
      - /home/jp/.orion:/home/hal/.orion:rw

      # REMOVED: /home/jp/orion:/app:ro  (code is now inside the image)

      # Config (secrets) — read-only single file
      - /home/jp/orion/.env:/app/.env:ro

      # Infrastructure configs — read-only
      - /opt/homelab-infrastructure:/mnt/infra:ro

      # Reference documents — read-only
      - /data/orion:/mnt/data:ro

      # Falco logs — read-only
      - /var/log/falco:/mnt/falco:ro

      # Host system configs — read-only
      - /etc:/mnt/host-etc:ro

      # SSH key for service account — read-only
      - /home/jp/.ssh/hal-svc:/home/hal/.ssh/id_ed25519:ro
```

Changes:

- Added `image: ghcr.io/jeanpaul-source/orion:latest`
- Removed `build:` block (image comes from GHCR, not local build)
- Removed `/home/jp/orion:/app:ro` bind mount (code is inside the image)
- `.env` mount stays — secrets must not be baked into images

**Step 3 — Rewrite `deploy.yml`:**

```yaml
name: Deploy to the-lab

on:
  workflow_run:
    workflows: ["Build and push image"]
    types: [completed]
    branches: [main]

jobs:
  deploy:
    name: Deploy to the-lab
    runs-on: self-hosted
    if: github.event.workflow_run.conclusion == 'success'

    steps:
      - name: Pull latest image
        run: docker pull ghcr.io/jeanpaul-source/orion:latest

      - name: Restart container
        run: |
          cd ~/orion
          docker compose up -d

      - name: Show container logs
        if: always()
        run: docker logs --tail 20 orion
```

Changes:

- Triggers on `workflow_run` (after build succeeds), not on push directly
- No `git pull` — the image has the code
- No change detection — every deploy pulls the latest image and restarts
- `cd ~/orion` stays because that's where `docker-compose.yml` lives
  (the dev workspace). This is fine because compose only reads the YAML,
  it doesn't use the source code.

**Step 4 — Authenticate Docker on the server for GHCR pulls:**

```bash
# On the-lab, one-time setup
echo "$GITHUB_PAT" | docker login ghcr.io -u jeanpaul-source --password-stdin
```

The self-hosted runner needs to pull from GHCR. For a public repo the images
are public, so this step may not be needed. Test first without auth.

**Step 5 — Migrate the running container:**

```bash
# Pull the first image (CI must have run at least once first)
docker pull ghcr.io/jeanpaul-source/orion:latest

# Restart with the new compose config
cd ~/orion
docker compose up -d
# Docker will recreate the container using the GHCR image

# Verify
curl http://localhost:8087/health
```

Note: `docker compose up -d` detects that the image/config changed and
recreates the container automatically. No need for `docker compose down` first.

**Step 6 — Update shell aliases in `~/.bashrc`:**

```bash
alias orion-update="docker pull ghcr.io/jeanpaul-source/orion:latest && cd ~/orion && docker compose up -d"
alias orion-rollback='f() { docker pull ghcr.io/jeanpaul-source/orion:"$1" && cd ~/orion && IMAGE_TAG="$1" docker compose up -d; }; f'
```

**Step 7 — Update OPERATIONS.md and CONTRIBUTING.md:**

Document the image-based deploy model:

- CI builds and pushes to GHCR on every merge to `main`
- The server pulls the image and restarts the container
- `~/orion` is the dev workspace AND where `docker-compose.yml` lives
- The source code is inside the image, not bind-mounted
- Rollback: `docker pull ghcr.io/jeanpaul-source/orion:<sha> && docker compose up -d`

Remove the old "update code + restart" deploy instructions.

#### Acceptance Criteria

- [ ] `.github/workflows/build.yml` exists and runs on push to `main`
- [ ] GHCR shows `ghcr.io/jeanpaul-source/orion:latest` image
- [ ] `docker-compose.yml` uses `image:` instead of `build:`, no source bind mount
- [ ] `deploy.yml` does `docker pull` + `docker compose up -d`, no `git pull`
- [ ] `curl http://localhost:8087/health` returns 200
- [ ] Switch to a feature branch in `~/orion` — deploy still works (image is independent)
- [ ] OPERATIONS.md documents image-based deploy model
- [ ] CONTRIBUTING.md deploy section updated
- [ ] `make check` passes

#### What Could Go Wrong

- **GHCR auth on self-hosted runner:** If the repo is public, images are public
  too — no auth needed for pulls. If private, the runner needs a PAT with
  `read:packages` scope stored in `~/.docker/config.json`.

- **First deploy chicken-and-egg:** The build workflow must run once before the
  deploy workflow can pull an image. Merge the build workflow first, let it run,
  then merge the deploy + compose changes.

- **Container downtime:** `docker compose up -d` with a changed image recreates
  the container. Expect ~30 seconds of downtime plus up to 120 seconds for the
  health check `start_period`. Plan for 2-3 minutes total.

- **Rollback:** Pull a previous image by SHA tag:

  ```bash
  docker pull ghcr.io/jeanpaul-source/orion:<previous-sha>
  # Edit docker-compose.yml to pin the tag, or:
  docker tag ghcr.io/jeanpaul-source/orion:<sha> ghcr.io/jeanpaul-source/orion:latest
  cd ~/orion && docker compose up -d
  ```

- **Dockerfile changes:** Since the image is built in CI (on `ubuntu-latest`),
  not on the server, multi-arch issues could arise. The server is x86_64 and
  `ubuntu-latest` is also x86_64, so this is fine.

#### Dependencies

None — but this must be done BEFORE Batch 4 (health check + notification).

#### Estimated Time

60-90 minutes (new workflow + compose/deploy edits + migration + docs).
There is a two-commit strategy to avoid the chicken-and-egg problem:

- Commit 1: Add `build.yml` → merge → wait for image to build
- Commit 2: Update `docker-compose.yml` + `deploy.yml` + docs → merge

---

## Batch 4 — CD Hardening

### Issue: Add health check and failure notification to deploy pipeline

**Title:** `fix: deploy health check + ntfy failure notification`

**Labels:** `ci-cd`, `guardrails`

#### Problem

Two remaining gaps in `deploy.yml` (after Batch 3 moves to image-based deploys):

1. **F-06 (P1):** Deploy "succeeds" (green workflow) even if the container is
   crash-looping. The container has a healthcheck (`curl /health`) but deploy.yml
   never checks it.

2. **F-07 (P2):** Failed deploys are only visible in the GitHub Actions UI. No
   push notification. A broken deploy can sit unnoticed for hours.

**Note:** F-08 (rebuild detection) and F-09 (SHA verification) are solved by
Batch 3's image-based deploy — every merge builds a fresh image, and the image
tag is the git SHA. No additional work needed.

#### Evidence

```yaml
# deploy.yml — after Batch 3
# docker pull + docker compose up -d
# docker logs (no health check)
# No failure notification step exists
```

#### Solution

Add health check and notification steps to `deploy.yml`:

```yaml
name: Deploy to the-lab

on:
  workflow_run:
    workflows: ["Build and push image"]
    types: [completed]
    branches: [main]

jobs:
  deploy:
    name: Deploy to the-lab
    runs-on: self-hosted
    if: github.event.workflow_run.conclusion == 'success'

    steps:
      - name: Pull latest image
        run: docker pull ghcr.io/jeanpaul-source/orion:latest

      - name: Restart container
        run: |
          cd ~/orion
          docker compose up -d

      # Wait for container to be healthy
      # The container has start_period: 120s, so we allow up to 150s

      - name: Wait for healthy container
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
            -d "Deploy of ${{ github.event.workflow_run.head_sha }} failed. Check: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}" \
            "${{ secrets.NTFY_URL }}" || true
```

**GitHub Secret needed:** Add `NTFY_URL` as a repository secret.

#### Acceptance Criteria

- [ ] Deploy with working code → health check passes → green
- [ ] Intentionally break the container → health check fails → workflow red → ntfy notification received
- [ ] `NTFY_URL` secret exists in GitHub repo settings

#### What Could Go Wrong

- **Health check timeout:** 150 seconds (30 × 5s) should cover the 120s
  `start_period`. Increase attempts if the container is slow to start.

- **ntfy URL missing:** The `|| true` prevents the notification step from
  failing the workflow if ntfy is unreachable.

#### Dependencies

**Batch 3 must be done first** — deploy.yml structure changes.

#### Estimated Time

20-30 minutes (deploy.yml edits + adding GitHub secret + testing).

---

## Batch 5 — Documentation Fixes

### Issue: Fix documentation inaccuracies across README, CONTRIBUTING, and ARCHITECTURE

**Title:** `docs: fix 5 documentation inaccuracies + update CLAUDE.md workflow`

**Labels:** `docs`

#### Problem

Five documentation inaccuracies that mislead developers or break links, plus
one workflow instruction file that conflicts with the current dev tooling:

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

6. **F-22 (P1):** CLAUDE.md's "stop and wait" proposal format and one-change-
   per-commit cycle were written for Claude Code terminal sessions. In VS Code
   with Copilot, these rules fight the tool — the user reviews actual diffs in
   the editor, not markdown proposal blocks. The plan doc intro also references
   the old workflow. Update CLAUDE.md to be tool-agnostic.

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

**F-22 — Update CLAUDE.md for tool-agnostic workflow:**

The current CLAUDE.md has two sections that assume Claude Code terminal sessions:

1. The `⛔ REQUIRED FORMAT — Before Every Code Change` section mandates a
   `### Item N` proposal block that the AI must emit and then stop. In VS Code
   Copilot, this is counterproductive — the user sees actual file diffs instead.

2. The `How I (Claude) Work With the Operator` section's rules ("explain before
   acting", "one change at a time", "say I'm guessing") are good principles but
   are framed as Claude Code-specific rituals.

Rewrite these sections to be tool-agnostic:

- **Keep the principles:** root-cause analysis, one logical change per commit,
  transparency about uncertainty, no bandaids.
- **Remove the ritual:** no mandatory proposal block format, no "stop and wait"
  instruction. Instead: "explain what you're changing and why in your commit
  message and PR description."
- **Add Copilot-aware guidance:** "In VS Code, the user reviews diffs directly.
  Make changes that are easy to review — small, focused, well-commented."

Also update the `.github/copilot-instructions.md` reference to CLAUDE.md so it
doesn't point users at stale workflow rules.

#### Dependencies

None. Can be done at any point, but doing it early improves every subsequent
session since the AI implementer won't fight against conflicting instructions.

#### Estimated Time

30-40 minutes (text edits across 3-4 files + verification).

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

### Session 1 — GitHub Settings + Git Config (~40 min) ✅

**Completed:** 2026-03-13. PR #32 merged.

F-22, F-01, F-12, F-02, F-03, F-04, F-05, F-18 all resolved.
CLAUDE.md updated for tool-agnostic workflow. Stale branches cleaned.
Local git config set. Commit-msg hook installed.

---

### Session 2 — Image-Based Deploy (~90 min) ✅

**Completed:** 2026-03-14. PR #33 (build workflow) + PR #34 (deploy switch) merged.

F-21, F-08, F-09 all resolved. Container running from
`ghcr.io/jeanpaul-source/orion:latest`. No source bind mount.
Deploy triggers via `workflow_run` after build succeeds.
OPERATIONS.md and CONTRIBUTING.md updated.

---

### Session 3 — CD Hardening (~30 min) ✅

**Completed:** 2026-03-14. PR #35 merged.

F-06, F-07 resolved. Deploy pipeline now health-checks the container
(50 × 5s polling loop, 250s timeout) and sends ntfy push notification on
failure. `NTFY_URL` repository secret added. OPERATIONS.md updated with
new deploy behavior.

---

### Session 4 — Documentation Fixes (~30 min) ✅

**Completed:** 2026-03-14. PR #36 merged.

F-13, F-14, F-15, F-16, F-17 resolved. CONTRIBUTING.md bypass claim
corrected. README.md Web UI status fixed and SESSION_FINDINGS link
repaired. ARCHITECTURE.md Tempo status updated. Hardcoded test counts
replaced with approximate language (~1200, ~35) across README.md and
CONTRIBUTING.md.

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
| Session 1 — GitHub + Git Config | ~40 min | ✅ Done |
| Session 2 — Image-Based Deploy | ~90 min | ✅ Done |
| Session 3 — CD Hardening | ~30 min | ✅ Done |
| Session 4 — Documentation | ~30 min | ✅ Done |
| Session 5 — Dependencies & Polish | ~45 min | P2-P3 |
| **Total** | **~4 hours** | |

Sessions 1-4 complete. Session 5 is the final remaining batch.

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

- **GHCR (GitHub Container Registry):** GitHub's built-in Docker image registry.
  Free for public repos. Images live at `ghcr.io/<owner>/<repo>:<tag>`.

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
