#!/usr/bin/env bash
# Cron (1st of each month, 06:00):  0 6 1 * * /path/to/supplier-compliance-agent/scripts/run_monthly.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PERIOD="$(date -d "$(date +%Y-%m-01) -1 month" +%Y-%m)"   # previous month (GNU date)
echo "$(date -Is) running compliance agent for ${PERIOD}" >> logs/cron.log

if [ "${USE_DOCKER:-0}" = "1" ]; then
  docker compose run --rm agent python -m agent.main --period "${PERIOD}" >> logs/cron.log 2>&1
else
  [ -f .venv/bin/activate ] && source .venv/bin/activate
  python -m agent.main --period "${PERIOD}" >> logs/cron.log 2>&1
fi
