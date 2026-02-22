#!/bin/bash
# ORION Infrastructure Deployment Script
# Deploys docker-compose configuration from laptop to host

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REMOTE_HOST="lab"
REMOTE_DIR="/mnt/nvme2/orion-project/setup"

echo -e "${BLUE}=== ORION Infrastructure Deployment ===${NC}"
echo ""

# Verify we're in the right directory
if [ ! -f "$SCRIPT_DIR/docker-compose.yml" ]; then
    echo -e "${RED}ERROR: docker-compose.yml not found in $SCRIPT_DIR${NC}"
    exit 1
fi

# Check for required files
echo "📋 Pre-deployment checks..."

if grep -q "EMBEDDING_MODEL_PREF=BAAI/bge-base-en-v1.5" docker-compose.yml; then
    echo -e "${GREEN}✓ BGE embedding model configured (768-dim)${NC}"
else
    echo -e "${RED}✗ BGE configuration not found${NC}"
    echo "Expected: EMBEDDING_MODEL_PREF=BAAI/bge-base-en-v1.5"
    exit 1
fi

if grep -q "EMBEDDING_MODEL_MAX_CHUNK_LENGTH=512" docker-compose.yml; then
    echo -e "${GREEN}✓ Chunk length configured (512 tokens)${NC}"
else
    echo -e "${YELLOW}⚠ Chunk length not set to 512${NC}"
fi

# Show what will be deployed
echo ""
echo "Files to deploy:"
echo "  • docker-compose.yml (BGE-configured)"
if [ -f ".env.production" ]; then
    echo "  • .env (from .env.production)"
fi
echo ""
echo "Destination: ${REMOTE_HOST}:${REMOTE_DIR}"
echo ""

# Confirm deployment
read -p "Deploy to host? (yes/no): " -r REPLY
echo
if [[ ! $REPLY =~ ^[Yy]es$ ]]; then
    echo "Deployment cancelled"
    exit 0
fi

# Create backup on host
echo ""
echo "📦 Creating backup on host..."
ssh ${REMOTE_HOST} "
    cd ${REMOTE_DIR}
    TIMESTAMP=\$(date +%Y%m%d-%H%M%S)
    
    if [ -f docker-compose.yml ]; then
        cp docker-compose.yml docker-compose.yml.backup-\$TIMESTAMP
        echo \"✓ Backed up docker-compose.yml\"
    fi
    
    if [ -f .env ]; then
        cp .env .env.backup-\$TIMESTAMP
        echo \"✓ Backed up .env\"
    fi
"

# Deploy docker-compose.yml
echo ""
echo "📤 Deploying configuration..."
scp docker-compose.yml ${REMOTE_HOST}:${REMOTE_DIR}/

# Deploy .env if production version exists
if [ -f ".env.production" ]; then
    scp .env.production ${REMOTE_HOST}:${REMOTE_DIR}/.env
    echo -e "${GREEN}✓ Deployed .env from .env.production${NC}"
else
    echo -e "${YELLOW}⚠ No .env.production found, skipping .env deployment${NC}"
fi

echo -e "${GREEN}✓ Files deployed${NC}"

# Verify deployment
echo ""
echo "✅ Verifying deployment..."
ssh ${REMOTE_HOST} "
    cd ${REMOTE_DIR}
    echo 'Files in ${REMOTE_DIR}:'
    ls -lh docker-compose.yml .env 2>/dev/null || ls -lh docker-compose.yml
    echo ''
    echo 'BGE configuration check:'
    if grep -q 'EMBEDDING_MODEL_PREF=BAAI/bge-base-en-v1.5' docker-compose.yml; then
        echo '✓ BGE-base-en-v1.5 configured'
    else
        echo '✗ BGE not found!'
        exit 1
    fi
"

# Ask about restarting services
echo ""
echo -e "${YELLOW}⚠️  Services need to be restarted for changes to take effect${NC}"
echo ""
read -p "Restart services now? (yes/no): " -r RESTART
echo

if [[ $RESTART =~ ^[Yy]es$ ]]; then
    echo "🔄 Restarting services..."
    ssh ${REMOTE_HOST} "
        cd ${REMOTE_DIR}
        docker compose down
        echo 'Waiting 5 seconds...'
        sleep 5
        docker compose up -d
        echo ''
        echo 'Waiting for services to start (30 seconds)...'
        sleep 30
        docker compose ps
    "
    echo -e "${GREEN}✓ Services restarted${NC}"
else
    echo ""
    echo "Services NOT restarted. To apply changes later, run:"
    echo "  ssh ${REMOTE_HOST} 'cd ${REMOTE_DIR} && docker compose down && docker compose up -d'"
fi

# Summary
echo ""
echo -e "${GREEN}=== Deployment Complete ===${NC}"
echo ""
echo "Configuration deployed to ${REMOTE_HOST}:${REMOTE_DIR}"
echo ""
echo "Next steps:"
echo "  1. Verify services: ssh ${REMOTE_HOST} 'docker compose -f ${REMOTE_DIR}/docker-compose.yml ps'"
echo "  2. Check BGE config: ssh ${REMOTE_HOST} 'docker exec orion-anythingllm env | grep EMBEDDING'"
echo "  3. Verify Qdrant empty: ssh ${REMOTE_HOST} 'curl -s http://localhost:6333/collections'"
echo ""
