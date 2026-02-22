#!/bin/bash
# ORION RAG Overnight Batch Ingestion Script
# Processes all documents in /mnt/nvme1/orion-data/documents/raw
# with checkpoint/resume capability and enhanced monitoring
#
# Usage:
#   ./overnight-batch-ingest.sh              # Start new batch
#   ./overnight-batch-ingest.sh --resume     # Resume from checkpoint
#
# Created: 2025-11-20

set -e  # Exit on error

# ============================================================================
# CONFIGURATION
# ============================================================================

# Load .env file (prefer Ansible-deployed, fallback to repository root)
# Priority:
#   1. Ansible-deployed: /mnt/nvme2/orion-project/setup/.env (lab host)
#   2. Repository root: $PROJECT_DIR/../../../.env (laptop dev)
if [ -f "/mnt/nvme2/orion-project/setup/.env" ]; then
    # Lab host - use Ansible-deployed .env
    set -a
    source "/mnt/nvme2/orion-project/setup/.env"
    set +a
    echo "Loaded .env from Ansible deployment: /mnt/nvme2/orion-project/setup/.env"
elif [ -f "$PROJECT_DIR/../../../.env" ]; then
    # Laptop dev - use repository root .env
    set -a
    source "$PROJECT_DIR/../../../.env"
    set +a
    echo "Loaded .env from repository root: $PROJECT_DIR/../../../.env"
else
    echo "WARNING: No .env file found. Set ANYTHINGLLM_API_KEY manually."
fi

# API Key (REQUIRED)
# Loaded from .env or expect ANYTHINGLLM_API_KEY to be exported before running this script.

# Service URLs (override via environment to match host bindings)
export QDRANT_URL="${QDRANT_URL:-http://127.0.0.1:6333}"
export ANYTHINGLLM_URL="${ANYTHINGLLM_URL:-http://192.168.5.10:3001}"
FORCE_LOOPBACK_QDRANT="${FORCE_LOOPBACK_QDRANT:-1}"

# Paths
DOCUMENT_ROOT="/mnt/nvme1/orion-data/documents/raw"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Logging
LOG_DIR="/tmp/orion-logs"
LOGFILE="$LOG_DIR/orion-overnight-$(date +%Y%m%d-%H%M%S).log"
CHECKPOINT_FILE="/tmp/orion-checkpoint.json"

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

check_service() {
    local service_url="$1"
    local service_name="$2"

    if curl -s --connect-timeout 5 "$service_url" >/dev/null 2>&1; then
        log "✓ $service_name is accessible"
        return 0
    else
        error "✗ $service_name is NOT accessible at $service_url"
        return 1
    fi
}

# ============================================================================
# PRE-FLIGHT CHECKS
# ============================================================================

log "======================================================================"
log "ORION RAG OVERNIGHT BATCH INGESTION"
log "======================================================================"
log "Logfile: $LOGFILE"
log "Checkpoint: $CHECKPOINT_FILE"
log "Document root: $DOCUMENT_ROOT"
log ""

# Ensure Qdrant uses loopback when the host binding is detected
if [ "$FORCE_LOOPBACK_QDRANT" = "1" ] && [[ "$QDRANT_URL" =~ 192\.168\.5\.10 ]]; then
    log "Detected host-bound Qdrant URL ($QDRANT_URL); using http://127.0.0.1:6333 instead."
    log "Set FORCE_LOOPBACK_QDRANT=0 to disable this rewrite."
    QDRANT_URL="http://127.0.0.1:6333"
    export QDRANT_URL
fi

log "AnythingLLM URL: $ANYTHINGLLM_URL"
log "Qdrant URL: $QDRANT_URL"
log ""

# Check if API key is set
if [ -z "$ANYTHINGLLM_API_KEY" ]; then  # pragma: allowlist secret
    error "ANYTHINGLLM_API_KEY is not set"  # pragma: allowlist secret
    error "Export it before running: export ANYTHINGLLM_API_KEY='your-key'"  # pragma: allowlist secret
    exit 1
fi

# Check if document root exists
if [ ! -d "$DOCUMENT_ROOT" ]; then
    error "Document root not found: $DOCUMENT_ROOT"
    exit 1
fi

# Check services
log "Checking service health..."
check_service "$ANYTHINGLLM_URL/api/v1/system/ping" "AnythingLLM API" || exit 1
check_service "$QDRANT_URL" "Qdrant" || exit 1
log ""

# Run pre-flight verification
log "Running pre-flight verification..."
cd "$PROJECT_DIR"
if python scripts/verify_ingestion.py 2>&1 | tee -a "$LOGFILE"; then
    log "✓ Pre-flight verification passed"
else
    log "⚠️  Pre-flight verification found issues (this may be normal for first run)"
fi
log ""

# ============================================================================
# RUN ORCHESTRATION
# ============================================================================

log "Starting ingestion orchestration..."
log "Started: $(date)"
log ""

# Build command
CMD="python -u src/orchestrator.py"
CMD="$CMD --document-root '$DOCUMENT_ROOT'"
CMD="$CMD --checkpoint '$CHECKPOINT_FILE'"
CMD="$CMD --api-key '$ANYTHINGLLM_API_KEY'"  # pragma: allowlist secret
CMD="$CMD --base-url '$ANYTHINGLLM_URL'"

# Check for resume flag
if [ "$1" = "--resume" ]; then
    log "RESUME MODE: Will skip already processed files"
    log "Loading checkpoint from: $CHECKPOINT_FILE"
fi

log "Command: $CMD"
log ""

# Execute with unbuffered output
cd "$PROJECT_DIR"
eval "$CMD" 2>&1 | tee -a "$LOGFILE"
EXIT_CODE=${PIPESTATUS[0]}

log ""
log "Orchestration completed with exit code: $EXIT_CODE"
log "Completed: $(date)"
log ""

# ============================================================================
# POST-RUN VERIFICATION
# ============================================================================

log "Running post-run verification..."
if python scripts/verify_ingestion.py 2>&1 | tee -a "$LOGFILE"; then
    log "✓ Post-run verification passed"
else
    log "⚠️  Post-run verification found issues - check logs"
    EXIT_CODE=1
fi

# ============================================================================
# SUMMARY
# ============================================================================

log ""
log "======================================================================"
log "BATCH INGESTION SUMMARY"
log "======================================================================"
log "Logfile: $LOGFILE"
log "Checkpoint: $CHECKPOINT_FILE"
log ""

# Extract key stats from log
UPLOADED=$(grep -c "^✓" "$LOGFILE" 2>/dev/null || echo "0")
FAILED=$(grep -c "^✗ \[FAILED\]" "$LOGFILE" 2>/dev/null || echo "0")

log "Documents uploaded: $UPLOADED"
log "Documents failed: $FAILED"
log ""

if [ $EXIT_CODE -eq 0 ]; then
    log "✅ BATCH INGESTION COMPLETED SUCCESSFULLY"
else
    log "❌ BATCH INGESTION COMPLETED WITH ERRORS (exit code: $EXIT_CODE)"
fi

log "======================================================================"
log ""

# Print monitoring commands
log "Monitoring Commands:"
log "  View full log:     tail -f $LOGFILE"
log "  View progress:     grep 'PROGRESS REPORT' $LOGFILE | tail -1"
log "  Count uploaded:    grep -c '^✓' $LOGFILE"
log "  Count failed:      grep -c '^✗ \[FAILED\]' $LOGFILE"
log "  View errors:       grep '^✗ \[FAILED\]' $LOGFILE"
log "  Resume batch:      $0 --resume"
log ""

exit $EXIT_CODE
