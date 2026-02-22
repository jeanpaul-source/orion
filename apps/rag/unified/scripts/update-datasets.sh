#!/bin/bash
#
# ORION Automated Dataset Update Script
#
# Purpose: Weekly/monthly scheduled updates for keeping datasets fresh
# Usage: ./update-datasets.sh [--dry-run]
#
# Designed to run via systemd timer on host (192.168.5.10)
# Updates multiple knowledge domains with latest documentation
#
# Created: 2025-11-17 (Consolidation Phase)

set -euo pipefail

# Configuration
ORION_BASE="${ORION_BASE:-/mnt/nvme1/orion}"
LOG_DIR="${ORION_BASE}/logs"
VENV_PATH="${ORION_BASE}/.venv"

# Logging
mkdir -p "$LOG_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/update_${TIMESTAMP}.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE"
}

# Dry run mode
DRY_RUN=""
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN="--dry-run"
    log_warning "Running in DRY RUN mode - no changes will be made"
fi

# Function: Update a single dataset
update_dataset() {
    local TERM="$1"
    local DOMAIN="$2"
    local COLLECTION="$3"
    local MAX_DOCS="${4:-50}"

    log_info "======================================"
    log_info "Updating: $TERM (domain: $DOMAIN)"
    log_info "======================================"

    # Harvest new documents
    log_info "Step 1/3: Harvesting documents..."
    if orion harvest \
        --term "$TERM" \
        --domain "$DOMAIN" \
        --max-docs "$MAX_DOCS" \
        --new-only \
        $DRY_RUN 2>&1 | tee -a "$LOG_FILE"; then
        log_success "Harvest completed"
    else
        log_error "Harvest failed for: $TERM"
        return 1
    fi

    # Process new documents
    log_info "Step 2/3: Processing documents..."
    if orion process \
        --domain "$DOMAIN" \
        --new-only \
        $DRY_RUN 2>&1 | tee -a "$LOG_FILE"; then
        log_success "Processing completed"
    else
        log_error "Processing failed for: $TERM"
        return 1
    fi

    # Embed new documents
    log_info "Step 3/3: Embedding to collection: $COLLECTION..."
    if orion embed \
        "$COLLECTION" \
        --new-only \
        $DRY_RUN 2>&1 | tee -a "$LOG_FILE"; then
        log_success "Embedding completed"
    else
        log_error "Embedding failed for: $TERM"
        return 1
    fi

    log_success "✓ Completed update: $TERM"
    echo "" | tee -a "$LOG_FILE"
}

# Function: Health check before starting
health_check() {
    log_info "Running health checks..."

    # Check Docker services
    if ! docker compose -f "${ORION_BASE}/../infrastructure/docker-compose.yml" ps | grep -q "Up"; then
        log_error "Docker services not running. Please start services first."
        exit 1
    fi

    # Check Qdrant
    if ! curl -s http://localhost:6333/collections > /dev/null; then
        log_error "Qdrant not responding"
        exit 1
    fi

    # Check vLLM
    if ! curl -s http://localhost:8000/health > /dev/null; then
        log_warning "vLLM not responding (optional, continuing...)"
    fi

    # Check virtual environment
    if [[ ! -d "$VENV_PATH" ]]; then
        log_error "Virtual environment not found at: $VENV_PATH"
        exit 1
    fi

    log_success "All health checks passed"
    echo "" | tee -a "$LOG_FILE"
}

# Function: Post-update summary
update_summary() {
    log_info "======================================"
    log_info "Update Summary"
    log_info "======================================"

    # Registry stats
    log_info "Checking registry statistics..."
    orion status 2>&1 | tee -a "$LOG_FILE"

    log_success "Update run completed successfully!"
    log_info "Full log: $LOG_FILE"
}

# Main execution
main() {
    log_info "======================================"
    log_info "ORION Weekly Dataset Update"
    log_info "Started: $(date)"
    log_info "======================================"
    echo "" | tee -a "$LOG_FILE"

    # Activate virtual environment
    log_info "Activating virtual environment..."
    source "$VENV_PATH/bin/activate"

    # Change to ORION directory
    cd "$ORION_BASE"

    # Health check
    health_check

    # Dataset updates
    # You can customize this list based on your needs

    # Technical Documentation Updates
    update_dataset "kubernetes autoscaling" "manuals" "technical-docs" 50
    update_dataset "proxmox gpu passthrough" "manuals" "technical-docs" 30
    update_dataset "docker swarm orchestration" "manuals" "technical-docs" 30
    update_dataset "nginx reverse proxy" "manuals" "technical-docs" 30

    # Academic Research Updates
    update_dataset "vector databases performance" "academic" "research-papers" 20
    update_dataset "retrieval augmented generation" "academic" "research-papers" 20
    update_dataset "semantic search algorithms" "academic" "research-papers" 20

    # Blog/Tutorial Updates
    update_dataset "homelab best practices" "blogs" "technical-docs" 40
    update_dataset "self-hosted AI" "blogs" "technical-docs" 40

    # GitHub Documentation Updates
    update_dataset "qdrant documentation" "github" "code-examples" 20
    update_dataset "vllm optimization" "github" "code-examples" 20

    # Summary
    update_summary

    log_info "======================================"
    log_info "ORION Update Complete"
    log_info "Finished: $(date)"
    log_info "======================================"
}

# Trap errors
trap 'log_error "Script failed at line $LINENO"' ERR

# Run main
main "$@"
