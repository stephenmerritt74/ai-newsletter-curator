#!/bin/bash
# run-digest.sh — Wrapper for cron: loads env, sends digest to Telegram
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="$PROJECT_DIR/logs/digest.log"
mkdir -p "$PROJECT_DIR/logs"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting digest run" >> "$LOG_FILE"

bash "$PROJECT_DIR/scripts/curator-env.sh" --write >> "$LOG_FILE" 2>&1

cd "$PROJECT_DIR"
source .venv/bin/activate

python scripts/send_digest.py >> "$LOG_FILE" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Digest complete" >> "$LOG_FILE"
