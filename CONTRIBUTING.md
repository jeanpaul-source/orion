# Contributing

Development workflow, testing requirements, and operating contract for Orion/HAL.

---

## Before making any change

Read [CLAUDE.md](CLAUDE.md).

CLAUDE.md is the AI operating contract — it defines the mandatory format for every code
change (explain root cause before acting, one change at a time, no band-aids). It also
explains the purpose of this discipline: preventing drift on a long-running project where
individual fixes can look correct in isolation while the system degrades overall.

The short version:

1. State root cause + proposed change + why it's correct long-term + confidence level
2. Wait for approval
3. Make exactly one change
4. Verify it works
5. Move to the next item

This applies to human contributors as much as AI ones.

---

## Dev machine setup

```bash
git clone https://github.com/jeanpaul-source/orion
cd orion
make dev-setup          # creates venv, installs deps, wires all hooks
cp .env.example .env
# Fill in PGVECTOR_DSN password
```

Or step by step:

```bash
python -m venv .venv && source .venv/bin/activate
pip install pip-tools
pip-sync requirements.lock requirements-dev.lock   # reproducible install from lock files
cp .env.example .env
.venv/bin/pre-commit install --install-hooks --overwrite
```

To update dependencies after editing `requirements.txt` or `requirements-dev.txt`:

```bash
.venv/bin/pip-compile requirements.txt --generate-hashes --allow-unsafe -o requirements.lock
.venv/bin/pip-compile requirements-dev.txt --generate-hashes --allow-unsafe -o requirements-dev.lock
pip-sync requirements.lock requirements-dev.lock
```

For eval work only (heavy install, server only):

```bash
.venv/bin/pip install -r requirements-eval.txt
```

Laptop `.env` should have:

```env
OLLAMA_HOST=http://192.168.5.10:11434
PROMETHEUS_URL=http://192.168.5.10:9091
LAB_HOST=192.168.5.10
LAB_USER=jp
USE_SSH_TUNNEL=false   # or true if ports are firewalled
PROM_PUSHGATEWAY=http://192.168.5.10:9092
HAL_INSTANCE=laptop
```

---

## Tests

**Run before every push. No exceptions.**

```bash
make test           # offline tests only (no Ollama needed) — 1176 tests
make test-full      # full suite including intent classifier (requires Ollama)
```

Or directly:

```bash
# Full suite (requires Ollama to be reachable — intent tests use live embeddings)
OLLAMA_HOST=http://192.168.5.10:11434 .venv/bin/pytest tests/ -v

# Offline tests only (no Ollama needed)
.venv/bin/pytest tests/ --ignore=tests/test_intent.py -v
```

1211 tests total:

- **35 intent classifier tests** — use live Ollama embeddings; require `OLLAMA_HOST` to be
  reachable. Run these on the server if you can't reach Ollama from the laptop.
- **1176 offline tests** — Judge, MemoryStore, agent loop, PlannerAgent/CriticAgent,
  trust_metrics, Telegram bot, parsers, harvest, prometheus trend, postmortem, evaluators.
  Run anywhere with no external services.

`pytest.ini` sets `pythonpath = .` so the `hal` package resolves without install.

If any test regresses, do not push. Fix it first.

---

## Linting and formatting

Ruff (lint + format) is enforced via pre-commit hooks and CI. Hooks fire on every `git commit`.
Markdown linting (`markdownlint-cli2`) also runs as a pre-commit hook. Rules are in `.markdownlint-cli2.yaml`.

```bash
make lint       # ruff check — catch errors and import issues
make lint-md    # markdownlint-cli2 — markdown formatting
make format     # ruff format — apply formatting
make typecheck  # mypy — type check hal/ (0 errors in baseline)
make coverage   # pytest-cov — show coverage report for hal/ (baseline: 87%)
make doc-drift  # check for documentation/code drift
make ratchet    # update .coverage-threshold to current coverage floor
make audit      # pip-audit — check for known vulnerabilities in dependencies
```

Or directly:

```bash
.venv/bin/ruff check hal/ tests/ harvest/ eval/          # lint
.venv/bin/ruff check --fix hal/ tests/ harvest/ eval/    # lint + auto-fix
.venv/bin/ruff format hal/ tests/ harvest/ eval/         # format
.venv/bin/mypy hal/                                      # type check
```

Three common lint failure patterns:

- **I001** — stdlib imports not in alphabetical order
- **E402** — import placed after module-level code (usually intentional `sys.path` manipulation — add to `per-file-ignores` in `pyproject.toml`)
- **F401** — unused import (delete it)

Commit readiness checklist (`make check` runs all of these):

- `make lint` passes
- `make lint-md` passes
- `make format` produces no diffs
- `make typecheck` passes (0 errors)
- `make test` passes (all offline tests)
- `make doc-drift` passes

---

## Evaluation

Run after any change that could affect response quality (intent routing, system prompt,
KB threshold, tool selection):

```bash
# Install eval deps first (server only — not in requirements-dev.lock)
.venv/bin/pip install -r requirements-eval.txt

# On the server (requires vLLM + Ollama + pgvector running)
python -m eval.run_eval                     # drives 40 queries → eval/responses.jsonl
python -m eval.evaluate --skip-llm-eval    # scores → eval/results/eval_out.json
```

Baselines (Feb 26, 2026):

- `intent_accuracy=100%` — all queries routed correctly
- `hal_identity=100%` — never identifies as Qwen
- `no_raw_json=100%` — no raw tool-call JSON in responses
- `web_tool_accuracy=100%` — web_search called when required

If any baseline regresses, investigate before merging.

---

## Git workflow

### Commit format

Use [Conventional Commits](https://www.conventionalcommits.org/). Every commit message
starts with a type prefix:

| Prefix | When to use |
| --- | --- |
| `feat:` | New capability or behaviour |
| `fix:` | Bug fix — something was wrong |
| `docs:` | Documentation only |
| `refactor:` | Code restructure, no behaviour change |
| `test:` | Adding or fixing tests |
| `chore:` | Tooling, deps, CI, formatting |
| `ci:` | CI/CD workflow changes |
| `perf:` | Performance improvement |
| `build:` | Build system or external dependencies |
| `revert:` | Revert a previous commit |

Subject line: imperative, lowercase, no period, ≤ 72 chars.
Body (optional): explain *why*, not *what*. The diff shows what; the body explains the
reasoning that isn't obvious from the code.

```plaintext
# Good
feat: add temporal awareness — snapshot diff across harvest runs
fix: raise KB seeding threshold to 0.75 — prevents low-confidence docs biasing agent

# Bad
Refactor and enhance HAL codebase     ← what changed? unknowable without reading the diff
wip                                   ← broken state committed to main
fix stuff                             ← which stuff?
```

### Commit granularity

**One logical change per commit.** A commit is ready when:

- `make test` passes (all 1176 offline tests)
- `make lint` passes
- `make lint-md` passes
- `make format` produces no diffs
- One thing changed with a clear description

Not one session. Not one keypress. One *thing*.

When Claude assists with a change, the natural commit boundary follows the CLAUDE.md
item cycle: one item approved → change made → verified → commit. If a session produces
five changes, that's five commits.

### Co-author tag

Any commit where Claude wrote substantial code gets:

```text
Co-Authored-By: Claude <noreply@anthropic.com>
```

Add it as the last line of the commit body. GitHub renders it as a co-author on the
commit view. It's standard practice for AI-assisted work and makes authorship honest.

### Branch policy

**`main` is always deployable.** The server runs `git pull` on `main`. A broken commit
on `main` means the server pulls broken code.

**PRs required to merge to `main`.** The `main-protection` ruleset requires CI to pass
before merge. Push to a feature branch, create a PR, let CI run, then merge:

```bash
git push origin feat/your-branch
# Create PR on GitHub — CI runs automatically
# Merge when green
```

For rapid solo iteration, you can still push feature branches freely. Direct push to
`main` is blocked by ruleset. The repository admin bypass actor allows emergency
direct pushes when genuinely needed.

Feel free to use long-lived feature branches. Squash to a clean commit before merging
when the history is noisy.

---

## Harvest (KB re-index)

Re-harvest after infrastructure changes (new service, changed config, new docs):

```bash
python -m harvest              # full run
python -m harvest --dry-run   # preview, no DB writes
```

The nightly timer handles routine updates. Manual runs are for when you've changed
something and need HAL to know about it now.

---

## Deploy

Deploys are image-based. CI builds a Docker image on every merge to `main` and pushes
it to GHCR (`ghcr.io/jeanpaul-source/orion`). The deploy workflow then pulls the new
image and recreates the container on the server. Source code lives inside the image —
there is no source code bind mount.

```bash
# Automatic: the CD pipeline runs on every merge to main.
# Manual fallback:
docker pull ghcr.io/jeanpaul-source/orion:latest
cd ~/orion && docker compose up -d

# Rollback to a specific commit:
docker pull ghcr.io/jeanpaul-source/orion:<git-sha>
docker tag ghcr.io/jeanpaul-source/orion:<git-sha> ghcr.io/jeanpaul-source/orion:latest
cd ~/orion && docker compose up -d
```

**Dev environment:** Code is written and pushed from the-lab (192.168.5.10) via VS Code
Remote SSH. The server holds a fine-grained GitHub PAT scoped to `jeanpaul-source/orion`,
permission `contents: write` only — no access to any other repo or account setting.

**Dev/deploy separation:** The dev workspace (`~/orion`) is no longer the deploy target.
The running container uses the image from GHCR, not a bind-mounted source tree. Local
edits do not affect the running container until they are pushed, merged, built, and
deployed.

**Credential path hardened:** `~/.config/git/credentials`, `~/.git-credentials`, and
`~/.netrc` are in the Judge's `_SENSITIVE_PATHS` — any HAL tool call targeting them
escalates by +1 tier (same treatment as `~/.ssh`).

---

## Server shortcuts

```bash
hal              # start HAL REPL
orion-update     # git pull

systemctl --user status vllm.service
systemctl --user restart vllm.service
journalctl --user -u vllm -f

systemctl --user status watchdog.timer
systemctl --user status harvest.timer
systemctl --user status telegram.service
```

---

## Key design constraints

These are not preferences — they are load-bearing decisions. Changing them without
understanding the rationale will break things:

- **Ollama is embeddings-only.** Setting `OLLAMA_NUM_GPU` to anything other than `0`
  will cause vLLM to OOM on the RTX 3090 Ti. See [ARCHITECTURE.md](ARCHITECTURE.md).
- **Prometheus is on 9091.** Port 9090 is Cockpit. The ports are never swapped.
- **vLLM requires two env vars** in the unit file (`VLLM_USE_FLASHINFER_SAMPLER=0`,
  `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`). Both are CUDA workarounds for the
  RTX 3090 Ti. Removing either causes crashes or OOMs under inference load.
- **The Judge has no bypass.** Every tool call goes through `judge.approve()`.
  There is no `force=True` parameter. If you need to add one, that's a CLAUDE.md-format
  conversation first.
