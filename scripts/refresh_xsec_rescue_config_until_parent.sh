#!/usr/bin/env bash
set -euo pipefail

PARENT_OUTPUT_JSON=""
SOURCE_ARTIFACT=""
OUT_PLAN=""
OUT_CONFIGS=""
TOP_K="16"
BUDGET_PER_SEED="16"
SLEEP_SEC="${REFRESH_XSEC_RESCUE_SLEEP_SEC:-600}"
ONCE="0"

usage() {
  cat >&2 <<'EOF'
usage: refresh_xsec_rescue_config_until_parent.sh \
  --parent-output-json PATH --source-artifact PATH --out-plan PATH --out-configs PATH \
  [--top-k N] [--budget-per-seed N] [--sleep-sec N] [--once]
EOF
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --parent-output-json) PARENT_OUTPUT_JSON="$2"; shift 2 ;;
    --source-artifact) SOURCE_ARTIFACT="$2"; shift 2 ;;
    --out-plan) OUT_PLAN="$2"; shift 2 ;;
    --out-configs) OUT_CONFIGS="$2"; shift 2 ;;
    --top-k) TOP_K="$2"; shift 2 ;;
    --budget-per-seed) BUDGET_PER_SEED="$2"; shift 2 ;;
    --sleep-sec) SLEEP_SEC="$2"; shift 2 ;;
    --once) ONCE="1"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

required=(PARENT_OUTPUT_JSON SOURCE_ARTIFACT OUT_PLAN OUT_CONFIGS)
for name in "${required[@]}"; do
  if [[ -z "${!name}" ]]; then
    echo "$name is required" >&2
    usage
    exit 2
  fi
done

for pair in "TOP_K:$TOP_K" "BUDGET_PER_SEED:$BUDGET_PER_SEED" "SLEEP_SEC:$SLEEP_SEC"; do
  name="${pair%%:*}"
  value="${pair#*:}"
  if ! [[ "$value" =~ ^[0-9]+$ ]] || [[ "$value" -lt 1 ]]; then
    echo "$name must be a positive integer" >&2
    exit 2
  fi
done

sha1_file() {
  python3 - "$1" <<'PY'
import hashlib
import pathlib
import sys

print(hashlib.sha1(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())
PY
}

json_list_len() {
  python3 - "$1" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text())
print(len(payload if isinstance(payload, list) else payload.get("configs", [])))
PY
}

refresh_once() {
  mkdir -p "$(dirname "$OUT_PLAN")" "$(dirname "$OUT_CONFIGS")"
  tmp_plan="${OUT_PLAN}.tmp.$$"
  tmp_configs="${OUT_CONFIGS}.tmp.$$"
  python3 scripts/v9_xsec_rescue_plan.py "$SOURCE_ARTIFACT" \
    --top-k "$TOP_K" \
    --budget-per-seed "$BUDGET_PER_SEED" \
    --out-plan "$tmp_plan" \
    --out-configs "$tmp_configs"
  mv "$tmp_plan" "$OUT_PLAN"
  mv "$tmp_configs" "$OUT_CONFIGS"
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) refreshed configs=$(json_list_len "$OUT_CONFIGS") sha1=$(sha1_file "$OUT_CONFIGS") source=$SOURCE_ARTIFACT"
}

while true; do
  if [[ -s "$PARENT_OUTPUT_JSON" ]]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) parent_exists; stop_refresh $PARENT_OUTPUT_JSON"
    exit 0
  fi
  refresh_once
  if [[ "$ONCE" == "1" ]]; then
    exit 0
  fi
  sleep "$SLEEP_SEC"
done
