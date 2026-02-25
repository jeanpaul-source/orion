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
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt   # pytest, azure-ai-evaluation
cp .env.example .env
# Fill in PGVECTOR_DSN password
```

Laptop `.env` should have:
```
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
# Full suite (requires Ollama to be reachable — intent tests use live embeddings)
OLLAMA_HOST=http://192.168.5.10:11434 .venv/bin/pytest tests/ -v

# Offline tests only (no Ollama needed)
.venv/bin/pytest tests/ -v -k "not require_ollama"
```

147 tests total:
- **35 intent classifier tests** — use live Ollama embeddings; require `OLLAMA_HOST` to be
  reachable. Run these on the server if you can't reach Ollama from the laptop.
- **112 offline tests** — Judge, MemoryStore, agent loop, PlannerAgent/CriticAgent,
  trust_metrics. Run anywhere with no external services.

`pytest.ini` sets `pythonpath = .` so the `hal` package resolves without install.

If any test regresses, do not push. Fix it first.

---

## Linting

Ruff is enforced via pre-commit. The pre-commit hook blocks pushes on lint failures.

```bash
# Run manually
.venv/bin/ruff check hal/ tests/ harvest/ eval/

# Auto-fix (safe changes only)
.venv/bin/ruff check --fix hal/ tests/ harvest/ eval/
```

Three common failure patterns:
- **I001** — stdlib imports not in alphabetical order
- **E402** — import placed after module-level code (usually intentional `sys.path` manipulation — add to `per-file-ignores` in `pyproject.toml`)
- **F401** — unused import (delete it)

---

## Evaluation

Run after any change that could affect response quality (intent routing, system prompt,
KB threshold, tool selection):

```bash
# On the server (requires vLLM + Ollama + pgvector running)
python -m eval.run_eval                     # drives 24 queries → eval/responses.jsonl
python -m eval.evaluate --skip-llm-eval    # scores → eval/results/eval_out.json
```

Baselines (Feb 23, 2026):
- `hal_identity=100%` — never identifies as Qwen
- `no_raw_json=100%` — no raw tool-call JSON in responses
- `intent_accuracy=95.8%` — 23/24 queries routed correctly

If any baseline regresses, investigate before merging.

---

## Git workflow

### Commit format

Use [Conventional Commits](https://www.conventionalcommits.org/). Every commit message
starts with a type prefix:

| Prefix | When to use |
|---|---|
| `feat:` | New capability or behaviour |
| `fix:` | Bug fix — something was wrong |
| `docs:` | Documentation only |
| `refactor:` | Code restructure, no behaviour change |
| `test:` | Adding or fixing tests |
| `chore:` | Tooling, deps, CI, formatting |

Subject line: imperative, lowercase, no period, ≤ 72 chars.
Body (optional): explain *why*, not *what*. The diff shows what; the body explains the
reasoning that isn't obvious from the code.

```
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
- `pytest tests/ -k "not require_ollama"` passes
- `ruff check hal/ tests/ harvest/ eval/` passes
- One thing changed with a clear description

Not one session. Not one keypress. One *thing*.

When Claude assists with a change, the natural commit boundary follows the CLAUDE.md
item cycle: one item approved → change made → verified → commit. If a session produces
five changes, that's five commits.

### Co-author tag

Any commit where Claude wrote substantial code gets:

```
Co-Authored-By: Claude <noreply@anthropic.com>
```

Add it as the last line of the commit body. GitHub renders it as a co-author on the
commit view. It's standard practice for AI-assisted work and makes authorship honest.

### Branch policy

**`main` is always deployable.** The server runs `git pull` on `main`. A broken commit
on `main` means the server pulls broken code.

Rule: tests and lint pass locally before `git push`.

Feature branches are optional — use one when exploring something that might not work and
you don't want to break `main` mid-experiment. When the experiment succeeds, squash it
into a clean commit on `main` and delete the branch. When it fails, delete the branch
without merging.

No PRs required for solo work.

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

```bash
# On laptop — push to GitHub
git push origin main

# On server — pull from GitHub
cd ~/orion && git pull    # alias: orion-update
```

**Rule: laptop pushes only. Server pulls only.** The server never has push credentials.
The deploy key at `~/.ssh/orion_deploy` is read-only.

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
