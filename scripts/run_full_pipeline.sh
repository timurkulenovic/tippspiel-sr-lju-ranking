#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

python_version_ok() {
  command -v "$1" >/dev/null 2>&1 \
    && "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null
}

python_has_deps() {
  "$1" -c 'import crawlee' 2>/dev/null
}

resolve_python() {
  local candidate candidates=()

  if [ -n "${PYTHON_BIN:-}" ]; then
    candidates=("$PYTHON_BIN")
  else
    if [ -x "${REPO_ROOT}/.venv/bin/python" ]; then
      candidates+=("${REPO_ROOT}/.venv/bin/python")
    fi
    candidates+=(
      python3.13 python3.12 python3.11
      /opt/anaconda3/envs/sportradar-general/bin/python3
      /opt/homebrew/bin/python3
      python3 python
    )
  fi

  for candidate in "${candidates[@]}"; do
    if python_version_ok "$candidate" && python_has_deps "$candidate"; then
      printf '%s' "$candidate"
      return 0
    fi
  done

  for candidate in "${candidates[@]}"; do
    if python_version_ok "$candidate"; then
      printf '%s' "$candidate"
      return 0
    fi
  done

  return 1
}

if ! PYTHON_BIN="$(resolve_python)"; then
  printf 'error: Python 3.11+ is required (tomllib is missing on older versions).\n' >&2
  printf 'Install Python 3.11+ or set PYTHON_BIN to a compatible interpreter, e.g.:\n' >&2
  printf '  PYTHON_BIN=/opt/homebrew/bin/python3 ./scripts/run_full_pipeline.sh\n' >&2
  exit 1
fi

if ! python_has_deps "$PYTHON_BIN"; then
  printf 'error: project dependencies are not installed for %s\n' "$PYTHON_BIN" >&2
  printf 'Run:\n' >&2
  printf '  %s -m pip install -e '"'"'.[dev]'"'"'\n' "$PYTHON_BIN" >&2
  printf '  %s -m playwright install chromium\n' "$PYTHON_BIN" >&2
  exit 1
fi

export PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"

CONFIG_FILE="${CONFIG_FILE:-${REPO_ROOT}/config.toml}"
RANKING_JSON="${RANKING_JSON:-${REPO_ROOT}/ranking.json}"
REPORT_JSON="${REPORT_JSON:-${REPO_ROOT}/ljubljana_ranking.json}"
OFFICE_FILTER="${OFFICE_FILTER:-Ljubljana}"
TIMEOUT_MS="${TIMEOUT_MS:-90000}"
HEADED_MODE="${HEADED_MODE:-auto}"

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$1"
}

log "Using Python interpreter: ${PYTHON_BIN} ($("$PYTHON_BIN" --version 2>&1))"
log "Using config file: ${CONFIG_FILE}"

crawl_headed_flag=()
case "${HEADED_MODE}" in
  true)
    crawl_headed_flag=(--headed)
    ;;
  false)
    crawl_headed_flag=()
    ;;
  auto)
    if [ -z "${CI:-}" ] && [ -z "${GITHUB_ACTIONS:-}" ]; then
      crawl_headed_flag=(--headed)
    fi
    ;;
  *)
    log "Invalid HEADED_MODE='${HEADED_MODE}'. Use: auto|true|false"
    exit 1
    ;;
esac

log "Step 1/2: crawling rankings into ${RANKING_JSON}"
"$PYTHON_BIN" -m tippspiel_crawler.crawl_ranking \
  --credentials-file "$CONFIG_FILE" \
  --out "$RANKING_JSON" \
  --timeout "$TIMEOUT_MS" \
  "${crawl_headed_flag[@]}"

log "Step 2/2: preparing ${OFFICE_FILTER} report data into ${REPORT_JSON}"
"$PYTHON_BIN" -m tippspiel_crawler.export_ranking_html \
  --input "$RANKING_JSON" \
  --office "$OFFICE_FILTER" \
  --config-file "$CONFIG_FILE" \
  --output "$REPORT_JSON"


log "Pipeline finished successfully"
log "Artifacts: ${RANKING_JSON} | ${REPORT_JSON}"

