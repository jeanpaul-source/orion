#!/bin/bash
# Generate Authelia Secrets
# Run this once during initial setup to generate secure random secrets

set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}Generating Authelia Secrets${NC}"
echo ""

# Generate secrets (64 characters each)
JWT_SECRET=$(openssl rand -hex 64)
SESSION_SECRET=$(openssl rand -hex 64)
STORAGE_ENCRYPTION_KEY=$(openssl rand -hex 64)

echo -e "${GREEN}✓ Secrets generated successfully${NC}"
echo ""
echo -e "${YELLOW}Add these to your .env file:${NC}"
echo ""
echo "# Authelia Secrets (generated $(date +%Y-%m-%d))"
echo "AUTHELIA_JWT_SECRET=$JWT_SECRET"
echo "AUTHELIA_SESSION_SECRET=$SESSION_SECRET"
echo "AUTHELIA_STORAGE_ENCRYPTION_KEY=$STORAGE_ENCRYPTION_KEY"
echo ""
echo -e "${YELLOW}CRITICAL:${NC} Never change AUTHELIA_STORAGE_ENCRYPTION_KEY after first use!"
echo "         Changing it will invalidate all existing user data and sessions."
echo ""
echo -e "${YELLOW}Security:${NC} Keep these secrets private. Do not commit them to git."
echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo "  1. Copy the above lines to: /mnt/nvme2/orion-project/setup/.env"
echo "  2. Set up at least one user: ./add-user.sh <username> <password> <email> <name>"
echo "  3. Deploy Authelia: docker compose -f docker-compose.traefik.yml -f docker-compose.authelia.yml up -d"
