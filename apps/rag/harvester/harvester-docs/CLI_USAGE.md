# ORION CLI — Complete Usage Guide

> **Part of the [ORION Autonomous Homelab AI System](../../README.md)**

---

## 📚 Quick Navigation

- 🏠 [Top-Level README](../../README.md) - System overview
- 📖 [ORION Endgame](../../docs/ORION-Endgame.md) - Vision and pipeline details
- ⚡ [Quick Start](../guides/QUICK_START.md) - Get running in 5 minutes
- 📜 [Timeline](../../docs/SESSION_HANDOFF.md) - Architectural history
- 🤖 [AI Agent Guide](../../.github/copilot-instructions.md) - Copilot instructions

---

## Installation

The unified `orion` CLI is now the preferred way to interact with the ORION pipeline.

```bash
# Install in development mode (from orion-harvester/)
pip install -e .

# Verify installation
orion --help
```

## Commands

- `orion query` — Query knowledge base with hybrid search + LLM
- `orion process` — Convert PDFs to AI-ready formats
- `orion embed-index` — Generate embeddings and index to Qdrant
- `orion validate` — Run data quality validators
- `orion ops` — Host operations (embed-serve, health, sync)

## Profiles

ORION uses profiles to manage multi-machine architecture. Profiles are defined in `config/orion.toml`.

Available profiles:
- **host** (default) — All compute on host; laptop orchestrates
- **laptop** — Same as host but enforces CPU-only safety
- **dev** — Local services for testing

### Using profiles

```bash
# Default (host profile)
orion query --test

# Explicit profile selection
orion --profile laptop query "How to configure Qdrant?"

# Via environment variable
export ORION_PROFILE=dev
orion query --test

# Verbose mode shows loaded config
orion --verbose --profile host query --help
```

## Examples

### Query knowledge base

```bash
# Test query
orion query --test --top-k 8

# Real question
orion query "What are Proxmox VE best practices?"

# With category filter
orion query --category homelab-infrastructure "network setup"
```

### Process library

```bash
# Process up to 50 files
orion process --max-files 50

# Custom input/output
orion process --input data/library --output data/processed

# Force reprocess
orion process --force
```

### Embed and index

```bash
# Default collection
orion embed-index

# Custom batch size and limit
orion embed-index --batch-size 64 --limit 100

# Specific collection
orion embed-index --collection orion_test

# ID validation controls (advanced)
# Use the underlying script directly to pass these flags
python scripts/embed_and_index.py --no-strict-ids                    # Disable strict ID validation/quarantine
python scripts/embed_and_index.py --quarantine-file logs/quarantine.jsonl  # Custom quarantine path
```

Notes
- The embedding pipeline enforces strict point ID validation by default to prevent Qdrant 400 errors from invalid IDs. Use `--no-strict-ids` to disable if you know your data is clean.
- Quarantine records are appended as JSONL to `logs/invalid_points_quarantine.jsonl` by default; override with `--quarantine-file <path>`.
- Advanced flags are currently available on the underlying script; the top-level `orion embed-index` command uses safe defaults.

### Data validation

```bash
# Quick validation
orion validate --quick

# Summary only
orion validate --summary
```

### Host operations

```bash
# Start embedding server on host
orion ops embed-serve

# Check health
orion ops embed-health

# Sync to host
orion ops sync

# Monitor services
orion ops monitor

# Legacy host manager (direct SSH helpers)
./scripts/host_embedding_manager.sh status   # one-time status snapshot
./scripts/host_embedding_manager.sh monitor  # auto-refresh dashboard (GPU, ETA, logs)
./scripts/host_embedding_manager.sh stop     # gracefully stop embedding run
./scripts/host_embedding_manager.sh clean    # rotate logs and quarantine
```

## Makefile shortcuts

The Makefile provides convenient aliases:

```bash
# Show help
make help

# Query
make query ARGS="--test --top-k 8"

# Process
make process ARGS="--max-files 50"

# Embedding server health
make ops-health

# With laptop profile
make query PROFILE=laptop ARGS="--test"
```

## Environment overrides

Profile settings can be overridden with environment variables:

```bash
# Override Qdrant URL
export ORION_QDRANT_URL=http://localhost:6333
orion query --test

# Override embedding service
export ORION_EMBED_URL=http://localhost:8001
orion query --test

# Force CPU (safety on laptop)
export ORION_FORCE_CPU=1
orion query --test

# Change log level
export ORION_LOG_LEVEL=DEBUG
orion --verbose query --test
```

## Migration from legacy scripts

The old script-based flow still works but is deprecated:

```bash
# OLD (still works)
bash scripts/orion.sh host query --test

# NEW (preferred)
orion query --test
```

All legacy scripts remain callable directly if needed:

```bash
python scripts/query_rag.py --test
python process_library.py --max-files 50
```

## Quality gates

Quality checks are integrated:

```bash
# Run full quality gate
bash scripts/quality_gate.sh

# Fast mode
bash scripts/quality_gate.sh --fast

# Via Makefile (coming soon)
make quality
```

## Tips

- Use `--verbose` to see loaded configuration and debug issues
- The `host` profile is optimized for the recommended two-machine setup
- Use `laptop` profile when running from laptop to enforce CPU-only safety
- All commands respect the same env vars (ORION_*) for consistency
