#!/bin/bash
#
# ORION Unified System Setup Script
#
# Purpose: Deploy unified ORION system on host (192.168.5.10)
# Usage: ./setup-host.sh [--skip-deps] [--skip-services-check]
#
# This script:
# 1. Creates directory structure
# 2. Copies code from existing applications
# 3. Sets up virtual environment
# 4. Installs dependencies
# 5. Configures systemd timer
# 6. Runs health checks
#
# Created: 2025-11-17 (Consolidation Phase)

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
ORION_BASE="${ORION_BASE:-/mnt/nvme1/orion}"
SKIP_DEPS=false
SKIP_SERVICES_CHECK=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-deps)
            SKIP_DEPS=true
            shift
            ;;
        --skip-services-check)
            SKIP_SERVICES_CHECK=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--skip-deps] [--skip-services-check]"
            exit 1
            ;;
    esac
done

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

# Function: Check if running on host
check_host() {
    log_info "Verifying we're running on the host..."

    # Check for expected host characteristics
    if [[ ! -d "/mnt/nvme1" ]] && [[ ! -d "/mnt/nvme2" ]]; then
        log_error "This doesn't appear to be the host machine (no /mnt/nvme1 or /mnt/nvme2)"
        log_error "This script should be run on 192.168.5.10 (lab host)"
        exit 1
    fi

    log_success "Running on host"
}

# Function: Check Docker services
check_docker_services() {
    if [[ "$SKIP_SERVICES_CHECK" == true ]]; then
        log_warning "Skipping Docker services check (--skip-services-check)"
        return 0
    fi

    log_info "Checking Docker services..."

    # Find docker-compose.yml
    COMPOSE_FILES=(
        "/mnt/nvme2/orion-project/setup/docker-compose.yml"
        "/root/orion/applications/orion-rag/infrastructure/docker-compose.yml"
    )

    COMPOSE_FILE=""
    for file in "${COMPOSE_FILES[@]}"; do
        if [[ -f "$file" ]]; then
            COMPOSE_FILE="$file"
            break
        fi
    done

    if [[ -z "$COMPOSE_FILE" ]]; then
        log_error "Could not find docker-compose.yml"
        log_error "Please ensure Docker services are running first"
        exit 1
    fi

    log_info "Found docker-compose.yml: $COMPOSE_FILE"

    # Check if services are running
    cd "$(dirname "$COMPOSE_FILE")"
    if ! docker compose ps | grep -q "Up"; then
        log_error "Docker services are not running"
        log_error "Start them with: cd $(dirname "$COMPOSE_FILE") && docker compose up -d"
        exit 1
    fi

    log_success "Docker services are running"
}

# Function: Create directory structure
create_directories() {
    log_info "Creating directory structure at: $ORION_BASE"

    mkdir -p "$ORION_BASE"/{src,data,config,scripts,logs}
    mkdir -p "$ORION_BASE"/src/{providers,processing,retrieval}
    mkdir -p "$ORION_BASE"/data/{raw/{academic,manuals,blogs,github},metadata,cache}

    log_success "Directory structure created"
}

# Function: Copy code from existing applications
copy_code() {
    log_info "Copying code from existing applications..."

    # Find source directories
    SOURCE_DIRS=(
        "/root/orion/applications/orion-rag"
        "/mnt/nvme2/orion-project/Laptop-MAIN/applications/orion-rag"
        "/home/user/Laptop-MAIN/applications/orion-rag"
    )

    SOURCE_DIR=""
    for dir in "${SOURCE_DIRS[@]}"; do
        if [[ -d "$dir" ]]; then
            SOURCE_DIR="$dir"
            break
        fi
    done

    if [[ -z "$SOURCE_DIR" ]]; then
        log_error "Could not find source directory (orion-rag)"
        log_error "Please ensure code is synced to host first"
        exit 1
    fi

    log_info "Source directory: $SOURCE_DIR"

    # Copy unified code (if exists)
    if [[ -d "$SOURCE_DIR/unified" ]]; then
        log_info "Copying unified code..."
        cp -r "$SOURCE_DIR/unified/src/"* "$ORION_BASE/src/"
        cp -r "$SOURCE_DIR/unified/scripts/"* "$ORION_BASE/scripts/"
        cp "$SOURCE_DIR/unified/requirements.txt" "$ORION_BASE/"

        # Copy configs if they exist
        if [[ -d "$SOURCE_DIR/unified/config" ]]; then
            cp -r "$SOURCE_DIR/unified/config/"* "$ORION_BASE/config/" 2>/dev/null || true
        fi
    fi

    # Copy providers from harvester
    if [[ -d "$SOURCE_DIR/harvester/src/providers" ]]; then
        log_info "Copying providers from harvester..."
        cp -r "$SOURCE_DIR/harvester/src/providers/"* "$ORION_BASE/src/providers/"
        cp "$SOURCE_DIR/harvester/src/provider_factory.py" "$ORION_BASE/src/providers/" 2>/dev/null || true
    fi

    # Copy processing modules from research-qa
    if [[ -d "$SOURCE_DIR/research-qa/src" ]]; then
        log_info "Copying processing modules from research-qa..."
        for file in orchestrator.py ingest.py registry.py anythingllm_client.py; do
            if [[ -f "$SOURCE_DIR/research-qa/src/$file" ]]; then
                cp "$SOURCE_DIR/research-qa/src/$file" "$ORION_BASE/src/processing/"
            fi
        done

        # Copy domains.py
        if [[ -f "$SOURCE_DIR/research-qa/src/domains.py" ]]; then
            cp "$SOURCE_DIR/research-qa/src/domains.py" "$ORION_BASE/src/"
        fi
    fi

    # Copy retrieval modules
    if [[ -d "$SOURCE_DIR/research-qa/src" ]]; then
        for file in hybrid_search.py reranker.py; do
            if [[ -f "$SOURCE_DIR/research-qa/src/$file" ]]; then
                cp "$SOURCE_DIR/research-qa/src/$file" "$ORION_BASE/src/retrieval/"
            fi
        done
    fi

    # Copy configurations
    if [[ -d "$SOURCE_DIR/harvester/config" ]]; then
        cp "$SOURCE_DIR/harvester/config/search_terms.csv" "$ORION_BASE/config/" 2>/dev/null || true
    fi

    if [[ -f "$SOURCE_DIR/research-qa/config/optimal-settings.yaml" ]]; then
        cp "$SOURCE_DIR/research-qa/config/optimal-settings.yaml" "$ORION_BASE/config/"
    fi

    log_success "Code copied successfully"
}

# Function: Setup virtual environment
setup_venv() {
    log_info "Setting up virtual environment..."

    cd "$ORION_BASE"

    if [[ -d ".venv" ]]; then
        log_warning "Virtual environment already exists, skipping creation"
    else
        python3 -m venv .venv
        log_success "Virtual environment created"
    fi

    # Activate and upgrade pip
    source .venv/bin/activate
    pip install --upgrade pip setuptools wheel > /dev/null

    log_success "Virtual environment ready"
}

# Function: Install dependencies
install_dependencies() {
    if [[ "$SKIP_DEPS" == true ]]; then
        log_warning "Skipping dependency installation (--skip-deps)"
        return 0
    fi

    log_info "Installing dependencies..."

    cd "$ORION_BASE"
    source .venv/bin/activate

    if [[ ! -f "requirements.txt" ]]; then
        log_error "requirements.txt not found"
        exit 1
    fi

    # Install dependencies
    pip install -r requirements.txt

    log_success "Dependencies installed"

    # Verify critical packages
    log_info "Verifying critical packages..."

    python3 -c "from sentence_transformers import CrossEncoder; print('✓ Reranking ready')" || log_error "sentence-transformers failed"
    python3 -c "from langchain.text_splitter import RecursiveCharacterTextSplitter; print('✓ Semantic chunking ready')" || log_error "langchain failed"
    python3 -c "from qdrant_client import QdrantClient; print('✓ Qdrant client ready')" || log_error "qdrant-client failed"
    python3 -c "import tiktoken; print('✓ Tokenizer ready')" || log_error "tiktoken failed"
    python3 -c "import typer; print('✓ CLI framework ready')" || log_error "typer failed"

    log_success "All critical packages verified"
}

# Function: Make CLI executable
setup_cli() {
    log_info "Setting up CLI..."

    # Make CLI executable
    chmod +x "$ORION_BASE/src/cli.py"

    # Create symlink
    if [[ -L "/usr/local/bin/orion" ]]; then
        log_warning "CLI symlink already exists"
    else
        ln -s "$ORION_BASE/src/cli.py" /usr/local/bin/orion
        log_success "CLI symlink created: /usr/local/bin/orion"
    fi

    # Test CLI
    if orion --help > /dev/null 2>&1; then
        log_success "CLI is working"
    else
        log_error "CLI test failed"
        exit 1
    fi
}

# Function: Setup systemd timer
setup_systemd() {
    log_info "Setting up systemd timer..."

    # Copy service and timer files
    if [[ -f "$ORION_BASE/scripts/orion-update.service" ]]; then
        cp "$ORION_BASE/scripts/orion-update.service" /etc/systemd/system/
    else
        log_warning "orion-update.service not found, skipping"
        return 0
    fi

    if [[ -f "$ORION_BASE/scripts/orion-update.timer" ]]; then
        cp "$ORION_BASE/scripts/orion-update.timer" /etc/systemd/system/
    else
        log_warning "orion-update.timer not found, skipping"
        return 0
    fi

    # Reload systemd
    systemctl daemon-reload

    # Enable timer (but don't start yet)
    systemctl enable orion-update.timer

    log_success "Systemd timer configured (not started)"
    log_info "Start with: systemctl start orion-update.timer"
}

# Function: Health check
health_check() {
    log_info "Running health checks..."

    cd "$ORION_BASE"
    source .venv/bin/activate

    # Run integration module health check
    if python3 src/integration.py; then
        log_success "Health check passed"
    else
        log_warning "Health check had issues (check logs above)"
    fi
}

# Function: Create .env file
create_env_file() {
    log_info "Creating .env file..."

    if [[ -f "$ORION_BASE/.env" ]]; then
        log_warning ".env file already exists, skipping"
        return 0
    fi

    cat > "$ORION_BASE/.env" << 'EOF'
# ORION Environment Configuration
# Created by setup script

# Base directory
ORION_BASE_DIR=/mnt/nvme1/orion

# Service URLs
QDRANT_URL=http://localhost:6333
ANYTHINGLLM_URL=http://localhost:3001
VLLM_URL=http://localhost:8000

# API Keys (REQUIRED - update these!)
ANYTHINGLLM_API_KEY=your-api-key-here

# Logging
LOG_LEVEL=INFO
EOF

    log_success ".env file created"
    log_warning "IMPORTANT: Update ANYTHINGLLM_API_KEY in $ORION_BASE/.env"
}

# Main execution
main() {
    log_info "======================================"
    log_info "ORION Unified System Setup"
    log_info "======================================"
    echo

    check_host
    check_docker_services
    create_directories
    copy_code
    setup_venv
    install_dependencies
    setup_cli
    create_env_file
    setup_systemd
    health_check

    log_info ""
    log_info "======================================"
    log_success "Setup Complete!"
    log_info "======================================"
    echo
    log_info "Next steps:"
    log_info "1. Update API key: nano $ORION_BASE/.env"
    log_info "2. Test CLI: orion status"
    log_info "3. Start timer: systemctl start orion-update.timer"
    log_info "4. Run test: orion harvest --term 'kubernetes' --domain manuals --max-docs 10"
    echo
}

# Trap errors
trap 'log_error "Setup failed at line $LINENO"' ERR

# Run main
main "$@"
