# ORION Makefile: simple ergonomics layer
# Use PROFILE=host (default) or PROFILE=laptop
# NEW: Prefer `orion` CLI over legacy scripts/orion.sh
# Examples:
#   make query ARGS="--test --top-k 8"
#   make process ARGS="--max-files 50"
#   make embed-serve
#
# IMPORTANT: Run 'source activate.sh' first to activate correct venv

PROFILE ?= host
ORION_CLI = .venv/bin/orion --profile $(PROFILE)
ORION_LEGACY = ./scripts/orion.sh $(PROFILE)

.PHONY: help
help:
	@echo "ORION Makefile (unified CLI)"
	@echo ""
	@echo "Commands (via orion CLI):"
	@echo "  make query        - Query knowledge base"
	@echo "  make process      - Convert PDFs to AI-ready formats"
	@echo "  make embed-index  - Generate embeddings and index"
	@echo "  make validate     - Run data validators"
	@echo "  make ops-serve    - Start host embedding server"
	@echo "  make ops-health   - Check embedding server health"
	@echo "  make quality      - Run quality gate (fast)"
	@echo "  make quality-full - Run full quality gate"
	@echo ""
	@echo "Profile: $(PROFILE) (set PROFILE=laptop to override)"
	@echo ""
	@echo "Examples:"
	@echo "  make query ARGS=\"--test --top-k 8\""
	@echo "  make process ARGS=\"--max-files 50\""
	@echo "  make embed-index ARGS=\"--batch-size 64\""

.PHONY: query
query:
	@bash scripts/check_venv.sh || exit 1
	@$(ORION_CLI) query $(ARGS)

.PHONY: process
process:
	@bash scripts/check_venv.sh || exit 1
	@$(ORION_CLI) process $(ARGS)

.PHONY: embed-index
embed-index:
	@bash scripts/check_venv.sh || exit 1
	@$(ORION_CLI) embed-index $(ARGS)

.PHONY: validate
validate:
	@$(ORION_CLI) validate $(ARGS)

.PHONY: ops-serve
ops-serve:
	@$(ORION_CLI) ops embed-serve

.PHONY: ops-health
ops-health:
	@$(ORION_CLI) ops embed-health

# Quality gate
.PHONY: quality
quality:
	@echo "Running quality gate..."
	@bash scripts/quality_gate.sh --fast

.PHONY: quality-full
quality-full:
	@echo "Running full quality gate..."
	@bash scripts/quality_gate.sh

# Legacy wrapper targets (for backward compat)
.PHONY: rechunk-check
rechunk-check:
	@$(ORION_LEGACY) rechunk-check $(ARGS)

.PHONY: embed-serve
embed-serve:
	@$(ORION_LEGACY) embed-serve $(ARGS)

.PHONY: embed-health
embed-health:
	@$(ORION_LEGACY) embed-health
