#!/usr/bin/env bash
#
# If all GPUs have utilization below a threshold (default 30%) for two
# consecutive checks, restart the transcribe_runner container.
# Run on the GPU host, e.g. via cron every 2–5 minutes.
#
# Usage:
#   ./restart_if_gpus_idle.sh [CONTAINER_NAME] [THRESHOLD] [INTERVAL] [GPU_IDS]
# Example (monitor only GPUs 2,3):
#   ./restart_if_gpus_idle.sh transcribe_runner 30 60 2,3
#
# Cron example (every 3 minutes):
#   */3 * * * * /path/to/transcribe_runner/scripts/restart_if_gpus_idle.sh transcribe_runner 30 60
#

set -e

CONTAINER_NAME="${1:-transcribe_runner}"
THRESHOLD="${2:-30}"
INTERVAL="${3:-60}"
# Only monitor GPUs 2,3 (transcribe uses these two)
GPU_IDS="${4:-2,3}"

# Require nvidia-smi
if ! command -v nvidia-smi &>/dev/null; then
  echo "nvidia-smi not found" >&2
  exit 1
fi

# Get GPU utilization for specified GPU ids only (one integer per line; N/A or empty => 0)
get_utilization() {
  nvidia-smi -i "$GPU_IDS" --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | while read -r line; do
    line="${line//%/}"
    line="${line// /}"
    if [[ -z "$line" || "$line" == "N/A" ]]; then
      echo 0
    else
      echo "$line"
    fi
  done
}

# Return 0 if any GPU has utilization >= THRESHOLD, else 1
any_gpu_busy() {
  local count=0
  while read -r util; do
    if [[ -n "$util" && "$util" =~ ^[0-9]+$ && "$util" -ge "$THRESHOLD" ]]; then
      return 0
    fi
    (( count++ )) || true
  done
  return 1
}

# First check
utils=$(get_utilization)
if echo "$utils" | any_gpu_busy; then
  exit 0
fi

# Wait and check again to avoid restart during brief idle
sleep "$INTERVAL"
utils=$(get_utilization)
if echo "$utils" | any_gpu_busy; then
  exit 0
fi

# Monitored GPUs (${GPU_IDS}) below threshold twice; restart container
if command -v docker &>/dev/null; then
  echo "$(date -Iseconds) GPUs ${GPU_IDS} below ${THRESHOLD}% for 2 checks; restarting container: ${CONTAINER_NAME}"
  docker restart "$CONTAINER_NAME"
else
  echo "docker not found" >&2
  exit 1
fi
