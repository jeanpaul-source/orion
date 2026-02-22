# ORION Harvester Optimization Status

> **Living Document** - Last updated: 2025-11-08  
> Part of the [ORION Autonomous Homelab AI System](../../README.md)

## Purpose

This document tracks all optimizations—completed, in-progress, and proposed—for the ORION Harvester system. It serves as a continuity log to ensure improvements align with [ORION-Endgame.md](../../docs/ORION-Endgame.md) goals: precision, freshness, groundedness, and operator experience.

## Current Status

- **Library Size:** 1,140 documents (203 in llm-serving-and-inference, 197 in gpu-passthrough-and-vgpu, 151 in homelab-infrastructure)
- **Acceptance Rate:** ~38.5% (target: 30–40%)
- **Freshness Target:** <24h from harvest to searchable
- **Test Run Performance:** 7 seconds for 3-doc focused harvest (papers-only, single-term)

---

## Completed Optimizations

### 2025-11-08: Core UX & Precision Improvements

#### 1. CSV Category Filter
**Status:** ✅ Completed  
**Commit/Date:** 2025-11-08  
**Problem:** `--category` flag was ignored in CSV mode, causing runs to process all categories even when user specified a target.  
**Solution:** Added `category_filter` parameter to `process_search_terms()` that skips CSV rows not matching the specified category.  
**Impact:**
- CSV-mode runs now respect `--category` for focused growth.
- Reduces unnecessary API calls and evaluation time.
- Aligns with Endgame precision-first approach.

**Acceptance:**
- When `--category X` is passed without `--term`, only CSV rows with `category=X` are processed.
- Behavior unchanged when `--category` is omitted (all rows processed).
- Log message confirms filter is active: `📂 Category filter active: <name>`

**Usage:**
```bash
python orion_harvester.py --category llm-serving-and-inference --providers papers --max-docs 50
```

---

#### 2. "harvest" Subcommand Alias
**Status:** ✅ Completed  
**Commit/Date:** 2025-11-08  
**Problem:** Muscle memory expects `harvest` as a subcommand, but script only supported flags directly or `run`.  
**Solution:** Added `"harvest"` to the set of recognized command aliases alongside `"run"` and flag-based invocation.  
**Impact:**
- Improved CLI ergonomics and reduced user error.
- No functional change; purely syntactic sugar.

**Acceptance:**
- `python orion_harvester.py harvest [flags]` works identically to `python orion_harvester.py [flags]`.
- Help text updated to show `harvest` as optional keyword.

**Usage:**
```bash
python orion_harvester.py harvest --term "vllm serving" --category llm-serving-and-inference --providers papers --max-docs 3
```

---

#### 3. Quiet Mode & Diagnostics Output
**Status:** ✅ Completed (wired, implementation pending in log sites)  
**Commit/Date:** 2025-11-08  
**Problem:** Large runs produce noisy per-candidate logs; diagnostics are valuable but clutter stdout.  
**Solution:**
- Added `--quiet` flag to suppress per-candidate accept/reject logs.
- Added `--diagnostics-out <path>` to write detailed decision logs (JSONL format) to disk without polluting stdout.
- Flags wired through `harvest_single_term()` and `process_search_terms()`.

**Impact:**
- Cleaner terminal output for large bulk runs.
- Detailed diagnostics available on-disk for post-run analysis without scrollback searching.
- Aligns with Endgame observability goals (structured logs for metrics).

**Acceptance:**
- Default behavior unchanged (concise logs, no diagnostics).
- With `--quiet`, per-candidate logs suppressed; high-level summaries still shown.
- With `--diagnostics-out <path>`, JSONL file created with one entry per candidate decision (accepted/rejected/skipped, reason, relevance score, etc.).
- `--diagnostics` continues to print to stdout unless `--quiet` also specified.

**Next Steps:**
- Wire `quiet` and `diagnostics_out` into actual logging sites (currently function signatures updated, awaiting implementation in log statements).
- Define JSONL schema for diagnostics output.

**Usage:**
```bash
python orion_harvester.py harvest --category vector-databases --providers papers --max-docs 100 --quiet --diagnostics-out /tmp/harvest_diagnostics.jsonl
```

---

## In-Progress Optimizations

### Rate Limit Intelligence
**Status:** 🚧 Proposed (not started)  
**Target Date:** TBD  
**Problem:** Fixed 5-second `RATE_LIMIT_DELAY` slows runs even when providers signal comfortable quotas.  
**Solution:**
- Respect rate-limit headers (e.g., `X-RateLimit-Remaining`, `Retry-After`).
- Skip or reduce delay when quota is ample; backoff aggressively on 429 or low remaining quota.
- Per-provider delay tuning (academic APIs vs. GitHub/SO).

**Expected Impact:**
- 20–40% faster bulk runs without risking bans.
- Better API citizenship (avoid hitting limits unnecessarily).

**Acceptance Criteria:**
- Average inter-request delay drops when headers show >50% quota remaining.
- On 429 or rate-limit warning, exponential backoff applied.
- Logs show per-provider delay decisions.

**Blocking:** None; safe to implement incrementally.

---

### Candidate Evaluation Cap
**Status:** 🚧 Proposed (not started)  
**Target Date:** TBD  
**Problem:** `--max-docs` limits downloads, but evaluation (fetching + filtering candidates) is unbounded, leading to slow dry-runs.  
**Solution:** Add `--max-candidates-per-provider <N>` to stop fetching/evaluating beyond N candidates per provider per term.  
**Expected Impact:**
- Faster dry-runs and exploratory runs.
- Prevents "accepted" log spam when only interested in first few high-quality matches.

**Acceptance Criteria:**
- With flag set, provider stops querying API after N candidates evaluated (regardless of accept/reject).
- Logs show: `Reached candidate limit (N) for <provider>, moving to next`.

**Blocking:** None; optional flag, default behavior unchanged.

---

## Proposed Optimizations (Future)

### 1. Default to "papers-only" for Ad-Hoc Runs
**Status:** 📋 Proposed  
**Priority:** Low (workflow change, not code)  
**Problem:** Default `--providers all` includes blogs/docs/GitHub/SO, increasing noise in quick tests.  
**Solution:** Document recommended defaults; optionally add config file support to set preferred provider list.  
**Expected Impact:** Faster, more focused test runs; academic sources align with Endgame grounding goals.  
**Acceptance:** Updated docs/guides recommend `--providers papers` for exploratory work.

---

### 2. Structured Observability Metrics
**Status:** 📋 Proposed  
**Priority:** Medium  
**Problem:** No Prometheus-friendly metrics for harvest runs; hard to track acceptance rates, provider latencies, rejection reasons over time.  
**Solution:**
- Emit counters: `orion_candidates_evaluated`, `orion_candidates_accepted`, `orion_candidates_rejected{reason="..."}`
- Emit histograms: `orion_provider_latency_seconds{provider="..."}`
- Expose metrics endpoint or write to file for Prometheus scraping.

**Expected Impact:**
- Grafana dashboards showing acceptance trends, provider health, rejection breakdowns.
- Aligns with Endgame SLO tracking (precision, recall, system reliability).

**Acceptance Criteria:**
- Metrics file or HTTP endpoint available post-run.
- Sample Grafana dashboard showing key KPIs.

**Blocking:** None; additive feature.

---

### 3. DOI/Citation Enrichment Pass
**Status:** 📋 Proposed  
**Priority:** Medium  
**Problem:** Some papers lack DOIs or normalized citation counts; reduces grounding strength.  
**Solution:**
- Post-download enrichment via Crossref/Unpaywall/OpenAlex APIs.
- Backfill missing DOIs, normalize author names, fetch updated citation counts.
- Run as separate script or `--enrich` flag.

**Expected Impact:**
- Higher "Average Citations" metric.
- Stronger source attribution in RAG answers.
- Better deduplication (DOI-based).

**Acceptance Criteria:**
- Script runs on existing library; updates `library_metadata.json` with enriched fields.
- No documents lost or corrupted.

**Blocking:** None; safe to run on stable library.

---

### 4. Near-Duplicate Detection
**Status:** 📋 Proposed  
**Priority:** Low  
**Problem:** Preprints and published versions (e.g., arXiv + conference) may both be harvested, causing duplication.  
**Solution:**
- Title normalization + shingled text hashing.
- Flag near-duplicates (>80% similarity); prompt user to keep one or merge metadata.

**Expected Impact:**
- Cleaner library; reduces embedding/storage cost.
- Improves retrieval precision (fewer redundant results).

**Acceptance Criteria:**
- Script identifies duplicate pairs; outputs report.
- User reviews and approves deletions/merges.

**Blocking:** None; can run after initial bulk harvest complete.

---

### 5. Auto-Process Integration
**Status:** 📋 Proposed  
**Priority:** High (for Freshness SLO)  
**Problem:** `--auto-process` flag exists but processing step (Stage 4) is manual in many workflows.  
**Solution:**
- Default `--auto-process` in scheduled (nightly/weekly) runs.
- Ensure processing errors don't block harvest completion.
- Add `--skip-auto-process` if user wants download-only.

**Expected Impact:**
- Harvest → process → embed pipeline completes in <24h without manual intervention.
- Directly supports Endgame Freshness SLO.

**Acceptance Criteria:**
- Nightly cron/systemd job uses `--auto-process`.
- Processing failures logged but don't crash harvester; retries available.

**Blocking:** None; already implemented, just needs workflow adoption.

---

### 6. Semantic Filter Tuning (Optional GPU Acceleration)
**Status:** 📋 Proposed (optional)  
**Priority:** Low (not a bottleneck for small runs)  
**Problem:** Sentence-transformers embedding may not use GPU; model load time adds latency.  
**Solution:**
- Explicitly set `device="cuda"` when initializing `SentenceTransformer`.
- Batch encode titles/abstracts for better GPU utilization.

**Expected Impact:**
- Faster large-scale semantic filtering (hundreds+ candidates).
- Minimal benefit for 3-doc test runs (already 7s wall time).

**Acceptance Criteria:**
- `nvidia-smi` shows Python process using GPU during relevance checks.
- Logs confirm model loaded to CUDA.

**Blocking:** None; purely optional performance tuning.

---

## Scheduled Run Profiles (Recommended Defaults)

### Nightly Refresh (Precision-First)
**Goal:** Constant trickle of fresh, high-quality docs.  
**Flags:**
```bash
python orion_harvester.py harvest \
  --providers papers \
  --since 2024-01-01 \
  --new-only \
  --min-citations 5 \
  --max-docs unlimited \
  --auto-process \
  --quiet \
  --diagnostics-out /var/log/orion/nightly_harvest.jsonl
```

**Cadence:** Nightly (cron/systemd timer)  
**Expected Outcome:** 5–20 new high-signal papers/night; embedded and searchable within 24h.

---

### Weekly Breadth Run
**Goal:** Add non-paper sources (GitHub, docs, blogs, SO).  
**Flags:**
```bash
python orion_harvester.py harvest \
  --providers github,stackoverflow,official-docs,tech-blogs \
  --since <last-run-date> \
  --new-only \
  --max-docs 100 \
  --auto-process \
  --quiet
```

**Cadence:** Weekly (Sunday 02:00)  
**Expected Outcome:** Diverse sources; maintains multi-format library.

---

### Category Sprint (Focused Growth)
**Goal:** Rapidly grow specific category (e.g., llm-serving-and-inference).  
**Flags:**
```bash
python orion_harvester.py harvest \
  --category llm-serving-and-inference \
  --providers papers \
  --min-citations 10 \
  --max-docs 200 \
  --auto-process \
  --quiet
```

**Cadence:** Ad-hoc (when category needs boost)  
**Expected Outcome:** Targeted, high-quality growth in priority area.

---

## Acceptance Criteria Tied to Endgame SLOs

| SLO | Target | Current | Optimization Impact |
|-----|--------|---------|---------------------|
| **Freshness** | <24h harvest→searchable | TBD | Auto-process + nightly runs → meets target |
| **Acceptance Rate** | 30–40% | ~38.5% ✅ | CSV category filter + papers-first → maintains/improves |
| **Precision@10** | ≥70% | TBD (RAG eval pending) | Academic sources + min-citations → increases |
| **Groundedness** | ≥90% cite sources | TBD | DOI enrichment + citation tracking → supports |
| **Operator UX** | Minimal friction | Improved | Quiet logs + harvest alias + help text → cleaner |

---

## Change Log

- **2025-11-08:** Document created. CSV category filter, harvest alias, quiet/diagnostics-out flags implemented. Rate limiting, candidate cap, enrichment, and observability metrics proposed.

---

## Next Steps

1. **Implement quiet/diagnostics-out logging logic** at log sites (currently wired through function signatures).
2. **Define JSONL schema** for `--diagnostics-out` (fields: timestamp, term, category, provider, title, decision, reason, relevance_score, etc.).
3. **Test CSV category filter** with real runs; validate log output and performance.
4. **Document recommended scheduled run profiles** in guides (nightly/weekly cron examples).
5. **Propose rate-limit intelligence** as next optimization (implementation plan + acceptance tests).

---

## Related Documents

- [ORION-Endgame.md](../../docs/ORION-Endgame.md) - Vision and SLOs
- [CLI_USAGE.md](./CLI_USAGE.md) - Command reference
- [QUALITY_ASSURANCE.md](./QUALITY_ASSURANCE.md) - Validation workflows
- [QUICK_START.md](../guides/QUICK_START.md) - Getting started
