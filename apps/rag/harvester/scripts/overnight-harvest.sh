#!/bin/bash
# ORION Batch Harvest Script
# Processes all search terms from config/search_terms.csv overnight
# with checkpoint/resume capability
#
# Usage:
#   ./overnight-harvest.sh               # Start new harvest
#   ./overnight-harvest.sh --resume      # Resume from checkpoint
#   ./overnight-harvest.sh --dry-run     # Test without downloading
#
# Created: 2025-11-20

set -e  # Exit on error

# ============================================================================
# CONFIGURATION
# ============================================================================

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARVESTER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TERMS_FILE="$HARVESTER_DIR/config/search_terms.csv"

# Logging
LOG_DIR="/tmp/orion-harvest-logs"
LOGFILE="$LOG_DIR/harvest-$(date +%Y%m%d-%H%M%S).log"
CHECKPOINT_FILE="/tmp/orion-harvest-checkpoint.json"

# Harvest settings
PROVIDERS="${ORION_PROVIDERS:-academic}"  # Default to academic providers
MAX_DOCS="${ORION_MAX_DOCS:-50}"          # Max docs per term

# Create log directory
mkdir -p "$LOG_DIR"

# ============================================================================
# FUNCTIONS
# ============================================================================

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOGFILE"
}

error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" | tee -a "$LOGFILE" >&2
}

# ============================================================================
# PRE-FLIGHT CHECKS
# ============================================================================

log "======================================================================"
log "ORION BATCH HARVESTER"
log "======================================================================"
log "Logfile: $LOGFILE"
log "Checkpoint: $CHECKPOINT_FILE"
log "Terms file: $TERMS_FILE"
log "Providers: $PROVIDERS"
log "Max docs per term: $MAX_DOCS"
log ""

# Check if terms file exists
if [ ! -f "$TERMS_FILE" ]; then
    error "Terms file not found: $TERMS_FILE"
    exit 1
fi

# Count terms
TERM_COUNT=$(tail -n +2 "$TERMS_FILE" | wc -l)
log "Total search terms: $TERM_COUNT"
log ""

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    log "Activating virtual environment..."
    cd "$HARVESTER_DIR"
    source activate.sh || source .venv/bin/activate
fi

# ============================================================================
# RUN BATCH HARVEST
# ============================================================================

log "Starting batch harvest..."
log "Started: $(date)"
log ""

# Build command
CMD="python -u scripts/batch_harvest.py"
CMD="$CMD --terms-file '$TERMS_FILE'"
CMD="$CMD --providers '$PROVIDERS'"
CMD="$CMD --max-docs $MAX_DOCS"
CMD="$CMD --checkpoint '$CHECKPOINT_FILE'"

# Check for flags
DRY_RUN=false
RESUME=false

for arg in "$@"; do
    case $arg in
        --dry-run)
            DRY_RUN=true
            CMD="$CMD --dry-run"
            log "DRY RUN MODE: No files will be downloaded"
            ;;
        --resume)
            RESUME=true
            log "RESUME MODE: Will skip already processed terms"
            log "Loading checkpoint from: $CHECKPOINT_FILE"
            ;;
        --limit=*)
            LIMIT="${arg#*=}"
            CMD="$CMD --limit $LIMIT"
            log "LIMITED MODE: Processing only $LIMIT terms"
            ;;
    esac
done

log "Command: $CMD"
log ""

# Execute with unbuffered output
cd "$HARVESTER_DIR"
eval "$CMD" 2>&1 | tee -a "$LOGFILE"
EXIT_CODE=${PIPESTATUS[0]}

log ""
log "Batch harvest completed with exit code: $EXIT_CODE"
log "Completed: $(date)"
log ""

# ============================================================================
# SUMMARY
# ============================================================================

log "======================================================================"
log "HARVEST SUMMARY"
log "======================================================================"
log "Logfile: $LOGFILE"
log "Checkpoint: $CHECKPOINT_FILE"
log ""

# Extract key stats from log
FOUND=$(grep -c "Found:" "$LOGFILE" 2>/dev/null || echo "0")
DOWNLOADED=$(grep "Documents downloaded:" "$LOGFILE" | tail -1 | grep -o "[0-9]*" | head -1 || echo "0")

log "Search queries executed: $FOUND"
log "Documents downloaded: $DOWNLOADED"
log ""

if [ $EXIT_CODE -eq 0 ]; then
    log "✅ BATCH HARVEST COMPLETED SUCCESSFULLY"
else
    log "❌ BATCH HARVEST COMPLETED WITH ERRORS (exit code: $EXIT_CODE)"
fi

log "======================================================================"
log ""

# Print monitoring commands
log "Monitoring Commands:"
log "  View full log:     tail -f $LOGFILE"
log "  View progress:     grep 'PROGRESS REPORT' $LOGFILE | tail -1"
log "  Count downloaded:  grep 'Documents downloaded:' $LOGFILE | tail -1"
log "  Resume harvest:    $0 --resume"
log ""

exit $EXIT_CODE
