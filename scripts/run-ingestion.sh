#!/bin/bash
# run-ingestion.sh — Wrapper for launchd: loads env, runs ingestion
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="$PROJECT_DIR/logs/ingestion.log"
mkdir -p "$PROJECT_DIR/logs"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting ingestion run" >> "$LOG_FILE"

# Load secrets from keychain into .env (refreshes on each run)
bash "$PROJECT_DIR/scripts/curator-env.sh" --write >> "$LOG_FILE" 2>&1

# Run ingestion in project venv
cd "$PROJECT_DIR"
source .venv/bin/activate

python scripts/run_ingestion.py --source all --days 2 >> "$LOG_FILE" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Ingestion complete" >> "$LOG_FILE"
