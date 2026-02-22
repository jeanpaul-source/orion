#!/bin/bash
# Generate Self-Signed SSL Certificates for ORION
# Usage: ./generate-certs.sh [domain]
#
# This script creates self-signed certificates for local development
# For production with public domain, use Let's Encrypt (automatic via Traefik)

set -euo pipefail

# Configuration
DOMAIN="${1:-orion.lab}"
CERT_DIR="$(dirname "$0")/certs"
DAYS_VALID=3650  # 10 years

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Create cert directory
mkdir -p "$CERT_DIR"
echo -e "${GREEN}Creating certificate directory: $CERT_DIR${NC}"

# Generate private key
echo -e "${YELLOW}Generating private key...${NC}"
openssl genrsa -out "$CERT_DIR/$DOMAIN.key" 4096

# Create certificate config
cat > "$CERT_DIR/$DOMAIN.conf" <<EOF
[req]
default_bits = 4096
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_req

[dn]
C = US
ST = HomeLabState
L = HomeLabCity
O = ORION Homelab
OU = Infrastructure
CN = $DOMAIN

[v3_req]
subjectAltName = @alt_names
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[alt_names]
DNS.1 = $DOMAIN
DNS.2 = *.$DOMAIN
DNS.3 = localhost
IP.1 = 127.0.0.1
IP.2 = 192.168.5.10
IP.3 = 192.168.5.25
EOF

# Generate certificate
echo -e "${YELLOW}Generating self-signed certificate (valid for $DAYS_VALID days)...${NC}"
openssl req \
    -new \
    -x509 \
    -key "$CERT_DIR/$DOMAIN.key" \
    -out "$CERT_DIR/$DOMAIN.crt" \
    -days $DAYS_VALID \
    -config "$CERT_DIR/$DOMAIN.conf" \
    -extensions v3_req

# Set permissions
chmod 600 "$CERT_DIR/$DOMAIN.key"
chmod 644 "$CERT_DIR/$DOMAIN.crt"

# Display certificate info
echo -e "${GREEN}Certificate generated successfully!${NC}"
echo ""
echo -e "${YELLOW}Certificate Details:${NC}"
openssl x509 -in "$CERT_DIR/$DOMAIN.crt" -text -noout | grep -E "(Subject:|DNS:|IP Address:|Not Before|Not After )"

echo ""
echo -e "${GREEN}Files created:${NC}"
echo "  - $CERT_DIR/$DOMAIN.key (private key)"
echo "  - $CERT_DIR/$DOMAIN.crt (certificate)"
echo "  - $CERT_DIR/$DOMAIN.conf (config - can be deleted)"

echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Trust the certificate on your machine:"
echo "   - Linux: sudo cp $CERT_DIR/$DOMAIN.crt /usr/local/share/ca-certificates/ && sudo update-ca-certificates"
echo "   - macOS: sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain $CERT_DIR/$DOMAIN.crt"
echo "   - Windows: Import $CERT_DIR/$DOMAIN.crt to Trusted Root Certification Authorities"
echo ""
echo "2. Add to /etc/hosts:"
echo "   192.168.5.10  $DOMAIN"
echo ""
echo "3. Start Traefik:"
echo "   cd $(dirname "$CERT_DIR") && docker compose -f docker-compose.traefik.yml up -d traefik"

# Create ACME directory for Let's Encrypt
mkdir -p "$CERT_DIR/../acme"
touch "$CERT_DIR/../acme/acme.json"
chmod 600 "$CERT_DIR/../acme/acme.json"
echo -e "${GREEN}Created ACME directory for Let's Encrypt${NC}"

echo ""
echo -e "${GREEN}✓ Certificate setup complete!${NC}"
