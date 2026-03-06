#!/usr/bin/env bash
# deploy-tempo.sh — Deploy Grafana Tempo to the monitoring stack.
#
# Run on the-lab (192.168.5.10) from the Orion repo root:
#   bash ops/deploy-tempo.sh
#
# What this does:
#   1. Copies tempo.yaml config to the monitoring stack
#   2. Copies Grafana Tempo datasource provisioning file
#   3. Adds the Tempo service to docker-compose.yml (if not already present)
#   4. Restarts the monitoring stack
#
# Prerequisites:
#   - Monitoring stack at /opt/homelab-infrastructure/monitoring-stack/
#   - Docker Compose v2
#   - Run as a user with write access to the monitoring stack directory

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONITORING_STACK="/opt/homelab-infrastructure/monitoring-stack"
COMPOSE_FILE="${MONITORING_STACK}/docker-compose.yml"

echo "=== Deploy Grafana Tempo to monitoring stack ==="
echo ""

# -------------------------------------------------------------------
# 1. Copy Tempo config
# -------------------------------------------------------------------
echo "[1/4] Copying tempo.yaml → ${MONITORING_STACK}/tempo.yaml"
cp "${SCRIPT_DIR}/tempo.yaml" "${MONITORING_STACK}/tempo.yaml"

# -------------------------------------------------------------------
# 2. Copy Grafana datasource provisioning file
# -------------------------------------------------------------------
GRAFANA_DS_DIR="${MONITORING_STACK}/grafana/provisioning/datasources"
echo "[2/4] Copying datasource → ${GRAFANA_DS_DIR}/tempo.yaml"
mkdir -p "${GRAFANA_DS_DIR}"
cp "${SCRIPT_DIR}/grafana-tempo-datasource.yaml" "${GRAFANA_DS_DIR}/tempo.yaml"

# -------------------------------------------------------------------
# 3. Check if Tempo service already exists in docker-compose.yml
# -------------------------------------------------------------------
if grep -q '^\s*tempo:' "${COMPOSE_FILE}"; then
    echo "[3/4] Tempo service already in ${COMPOSE_FILE} — skipping."
else
    echo "[3/4] Add the following service to ${COMPOSE_FILE} under 'services:':"
    echo ""
    cat << 'SNIPPET'
  tempo:
    image: grafana/tempo:2
    container_name: tempo
    restart: unless-stopped
    command: ["-config.file=/etc/tempo.yaml"]
    ports:
      - "4318:4318"     # OTLP HTTP receiver (HAL traces)
      - "3200:3200"     # Tempo query API (Grafana datasource)
    volumes:
      - ./tempo.yaml:/etc/tempo.yaml:ro
      - tempo-data:/var/tempo
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "1"
SNIPPET
    echo ""
    echo "Also add under the top-level 'volumes:' key:"
    echo ""
    cat << 'VOLSNIPPET'
  tempo-data:
VOLSNIPPET
    echo ""
    echo ">>> After adding the snippet, re-run this script or proceed to step 4."
    echo ""
    read -rp "Have you added the Tempo service to docker-compose.yml? [y/N] " confirm
    if [[ "${confirm}" != "y" && "${confirm}" != "Y" ]]; then
        echo "Aborted. Add the service block and re-run."
        exit 1
    fi
fi

# -------------------------------------------------------------------
# 4. Restart monitoring stack
# -------------------------------------------------------------------
echo "[4/4] Restarting monitoring stack..."
cd "${MONITORING_STACK}"
docker compose up -d

echo ""
echo "=== Done ==="
echo ""
echo "Verify Tempo is running:"
echo "  docker ps | grep tempo"
echo "  curl -s http://localhost:3200/ready"
echo ""
echo "HAL configuration:"
echo "  Set OTLP_ENDPOINT=http://host.docker.internal:4318 in ~/orion/.env"
echo "  Then: docker compose restart  (in ~/orion/)"
echo ""
echo "Grafana:"
echo "  Open http://192.168.5.10:3001 → Explore → select 'Tempo' datasource"
echo "  Run a query in HAL, then search for service:hal traces"
