#!/bin/bash
# Authelia User Management Script
# Usage: ./add-user.sh <username> <password> <email> <displayname> [groups]
#
# This script generates password hashes and updates users_database.yml

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USERS_FILE="$SCRIPT_DIR/users_database.yml"
AUTHELIA_IMAGE="authelia/authelia:latest"

# Functions
print_usage() {
    echo -e "${BLUE}Authelia User Management${NC}"
    echo ""
    echo "Usage: $0 <username> <password> <email> <displayname> [groups]"
    echo ""
    echo "Arguments:"
    echo "  username     - Username (lowercase, no spaces)"
    echo "  password     - Password (will be hashed with argon2id)"
    echo "  email        - Email address"
    echo "  displayname  - Display name (quoted if contains spaces)"
    echo "  groups       - Comma-separated groups (default: users)"
    echo ""
    echo "Examples:"
    echo "  $0 john MySecurePass123 john@orion.lab \"John Doe\" admins,users"
    echo "  $0 jane Password456 jane@orion.lab \"Jane Smith\" users"
    echo ""
    echo "Available groups:"
    echo "  - admins:  Full access (Traefik dashboard, Prometheus, etc.)"
    echo "  - users:   Normal access (Grafana, n8n, AnythingLLM)"
    echo "  - viewers: Read-only access (Grafana dashboards)"
}

# Validate arguments
if [ "$#" -lt 4 ]; then
    print_usage
    exit 1
fi

USERNAME="$1"
PASSWORD="$2"
EMAIL="$3"
DISPLAYNAME="$4"
GROUPS="${5:-users}"  # Default to 'users' group

# Validate username (alphanumeric + underscore only)
if ! [[ "$USERNAME" =~ ^[a-z0-9_]+$ ]]; then
    echo -e "${RED}Error: Username must be lowercase alphanumeric (a-z, 0-9, _)${NC}"
    exit 1
fi

# Validate email
if ! [[ "$EMAIL" =~ ^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]]; then
    echo -e "${RED}Error: Invalid email format${NC}"
    exit 1
fi

# Check if user already exists
if grep -q "^  $USERNAME:" "$USERS_FILE" 2>/dev/null; then
    echo -e "${YELLOW}Warning: User '$USERNAME' already exists in $USERS_FILE${NC}"
    read -p "Overwrite? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
fi

# Generate password hash
echo -e "${YELLOW}Generating password hash (this may take a few seconds)...${NC}"
PASSWORD_HASH=$(docker run --rm "$AUTHELIA_IMAGE" authelia crypto hash generate argon2 --password "$PASSWORD" 2>/dev/null | grep '$argon2id')

if [ -z "$PASSWORD_HASH" ]; then
    echo -e "${RED}Error: Failed to generate password hash${NC}"
    echo "Make sure Docker is running and you have internet access to pull $AUTHELIA_IMAGE"
    exit 1
fi

echo -e "${GREEN}Password hash generated successfully${NC}"

# Parse groups
IFS=',' read -ra GROUP_ARRAY <<< "$GROUPS"

# Create user entry
USER_ENTRY="
  $USERNAME:
    displayname: \"$DISPLAYNAME\"
    password: \"$PASSWORD_HASH\"
    email: $EMAIL
    groups:"

for group in "${GROUP_ARRAY[@]}"; do
    group=$(echo "$group" | xargs)  # Trim whitespace
    USER_ENTRY="$USER_ENTRY
      - $group"
done

# Backup current users file
if [ -f "$USERS_FILE" ]; then
    cp "$USERS_FILE" "${USERS_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    echo -e "${GREEN}Backed up existing users file${NC}"
fi

# Check if user exists and remove old entry
if grep -q "^  $USERNAME:" "$USERS_FILE" 2>/dev/null; then
    # Remove old user entry (from username line until next user or end of users section)
    sed -i "/^  $USERNAME:/,/^  [a-z]/ { /^  $USERNAME:/d; /^  [a-z]/! d; }" "$USERS_FILE"
fi

# Add new user entry
# Find the "users:" line and append user after it
awk -v user="$USER_ENTRY" '
    /^users:/ {
        print
        print user
        next
    }
    { print }
' "$USERS_FILE" > "${USERS_FILE}.tmp" && mv "${USERS_FILE}.tmp" "$USERS_FILE"

echo ""
echo -e "${GREEN}✓ User added successfully!${NC}"
echo ""
echo -e "${BLUE}User Details:${NC}"
echo "  Username:    $USERNAME"
echo "  Email:       $EMAIL"
echo "  Display:     $DISPLAYNAME"
echo "  Groups:      $GROUPS"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "  1. Review the updated file: $USERS_FILE"
echo "  2. Restart Authelia container:"
echo "     ${BLUE}docker compose -f docker-compose.traefik.yml restart authelia${NC}"
echo "  3. User can now log in at: ${BLUE}https://orion.lab/${NC}"
echo ""
echo -e "${YELLOW}MFA Setup:${NC}"
echo "  - On first login, user will be prompted to set up 2FA"
echo "  - Scan QR code with: Google Authenticator, Authy, or 1Password"
echo "  - Keep backup codes in a safe place!"
