#!/usr/bin/env bash
# gpu-metrics.sh — Export GPU metrics for Prometheus node-exporter textfile collector.
#
# Writes node_gpu_temperature_celsius and node_gpu_vram_usage_percent to a .prom
# file that node-exporter's textfile collector picks up automatically.
#
# Requires: nvidia-smi on PATH.
# Runs via: gpu-metrics.timer (systemd user timer, every 15s).

set -euo pipefail

OUTDIR="/var/lib/node-exporter/textfiles"
OUTFILE="${OUTDIR}/gpu.prom"
TMPFILE="${OUTFILE}.tmp"

# nvidia-smi CSV: temperature.gpu, memory.used [MiB], memory.total [MiB]
read -r temp_c mem_used_mib mem_total_mib < <(
    nvidia-smi --query-gpu=temperature.gpu,memory.used,memory.total \
               --format=csv,noheader,nounits | tr -d ' '  | tr ',' ' '
)

# Compute VRAM usage percentage
vram_pct=$(awk "BEGIN {printf \"%.1f\", ${mem_used_mib} / ${mem_total_mib} * 100}")

cat > "${TMPFILE}" << PROM
# HELP node_gpu_temperature_celsius GPU temperature in degrees Celsius.
# TYPE node_gpu_temperature_celsius gauge
node_gpu_temperature_celsius{gpu="0"} ${temp_c}
# HELP node_gpu_vram_usage_percent GPU VRAM usage as a percentage.
# TYPE node_gpu_vram_usage_percent gauge
node_gpu_vram_usage_percent{gpu="0"} ${vram_pct}
# HELP node_gpu_vram_used_mib GPU VRAM used in MiB.
# TYPE node_gpu_vram_used_mib gauge
node_gpu_vram_used_mib{gpu="0"} ${mem_used_mib}
# HELP node_gpu_vram_total_mib GPU VRAM total in MiB.
# TYPE node_gpu_vram_total_mib gauge
node_gpu_vram_total_mib{gpu="0"} ${mem_total_mib}
PROM

# Atomic rename to avoid partial reads by node-exporter
mv "${TMPFILE}" "${OUTFILE}"
