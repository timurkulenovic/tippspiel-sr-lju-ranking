#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

export PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"

CONFIG_FILE="${CONFIG_FILE:-${REPO_ROOT}/config.toml}"
RANKING_JSON="${RANKING_JSON:-${REPO_ROOT}/ranking.json}"
HTML_FILE="${HTML_FILE:-${REPO_ROOT}/index.html}"
OFFICE_FILTER="${OFFICE_FILTER:-Ljubljana}"
TIMEOUT_MS="${TIMEOUT_MS:-90000}"

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$1"
}

log "Using Python interpreter: ${PYTHON_BIN}"
log "Using config file: ${CONFIG_FILE}"

log "Step 1/2: crawling rankings into ${RANKING_JSON}"
"$PYTHON_BIN" -m tippspiel_crawler.crawl_ranking \
  --credentials-file "$CONFIG_FILE" \
  --out "$RANKING_JSON" \
  --timeout "$TIMEOUT_MS"

log "Step 2/2: exporting ${OFFICE_FILTER} rankings to ${HTML_FILE}"
$PYTHON_BIN -m tippspiel_crawler.export_ranking_html \
  --input "$RANKING_JSON" \
  --office "$OFFICE_FILTER" \
  --config-file "$CONFIG_FILE" \
  --output "$HTML_FILE"


log "Pipeline finished successfully"
log "Artifacts: ${RANKING_JSON} | ${HTML_FILE}"

