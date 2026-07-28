#!/usr/bin/env bash
set -euo pipefail

PARENT_OUTPUT_JSON=""
OUTPUT_JSON=""
OUTPUT_MD=""
REPORT_JSON=""
CONFIG_LIST_JSON=""
DATA_SNAPSHOT=""
TASK_NAME=""
PRESET=""
FINGERPRINT=""
TRAIN_START="2017-08-01"
TRAIN_END="2024-06-30 23:59:59"
EMBARGO_START="2024-07-01"
BOOTSTRAP_ITERATIONS="100"
PRIOR_TRIALS="0"
POLL_SEC="${QUEUE_XSEC_RESCUE_POLL_SEC:-120}"
SLOT_POLL_SEC="${QUEUE_XSEC_RESCUE_SLOT_POLL_SEC:-300}"
MAX_PARALLEL_FACTORY="${QUEUE_XSEC_RESCUE_MAX_PARALLEL_FACTORY:-2}"
NICE_LEVEL="${QUEUE_XSEC_RESCUE_NICE:-5}"
REFRESH_BEFORE_RUN="0"
REFRESH_PLAN_JSON=""
REFRESH_TOP_K="16"
REFRESH_BUDGET_PER_SEED="16"

usage() {
  cat >&2 <<'EOF'
usage: queue_xsec_rescue_after_parent.sh \
  --parent-output-json PATH --output-json PATH --output-md PATH --report-json PATH \
  --config-list-json PATH --data-snapshot PATH --task-name NAME --preset PRESET \
  --fingerprint SHA1|auto --prior-trials N|auto [--train-start DATE] [--train-end TS] \
  [--embargo-start DATE] [--bootstrap-iterations N] [--max-parallel-factory N] \
  [--refresh-before-run] [--refresh-plan-json PATH] [--refresh-top-k N] \
  [--refresh-budget-per-seed N]
EOF
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --parent-output-json) PARENT_OUTPUT_JSON="$2"; shift 2 ;;
    --output-json) OUTPUT_JSON="$2"; shift 2 ;;
    --output-md) OUTPUT_MD="$2"; shift 2 ;;
    --report-json) REPORT_JSON="$2"; shift 2 ;;
    --config-list-json) CONFIG_LIST_JSON="$2"; shift 2 ;;
    --data-snapshot) DATA_SNAPSHOT="$2"; shift 2 ;;
    --task-name) TASK_NAME="$2"; shift 2 ;;
    --preset) PRESET="$2"; shift 2 ;;
    --fingerprint) FINGERPRINT="$2"; shift 2 ;;
    --prior-trials) PRIOR_TRIALS="$2"; shift 2 ;;
    --train-start) TRAIN_START="$2"; shift 2 ;;
    --train-end) TRAIN_END="$2"; shift 2 ;;
    --embargo-start) EMBARGO_START="$2"; shift 2 ;;
    --bootstrap-iterations) BOOTSTRAP_ITERATIONS="$2"; shift 2 ;;
    --max-parallel-factory) MAX_PARALLEL_FACTORY="$2"; shift 2 ;;
    --refresh-before-run) REFRESH_BEFORE_RUN="1"; shift ;;
    --refresh-plan-json) REFRESH_PLAN_JSON="$2"; shift 2 ;;
    --refresh-top-k) REFRESH_TOP_K="$2"; shift 2 ;;
    --refresh-budget-per-seed) REFRESH_BUDGET_PER_SEED="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

required=(
  PARENT_OUTPUT_JSON OUTPUT_JSON OUTPUT_MD REPORT_JSON CONFIG_LIST_JSON DATA_SNAPSHOT
  TASK_NAME PRESET FINGERPRINT PRIOR_TRIALS
)
for name in "${required[@]}"; do
  if [[ -z "${!name}" ]]; then
    echo "$name is required" >&2
    usage
    exit 2
  fi
done

if ! [[ "$POLL_SEC" =~ ^[0-9]+$ ]] || [[ "$POLL_SEC" -lt 1 ]]; then
  echo "QUEUE_XSEC_RESCUE_POLL_SEC must be a positive integer" >&2
  exit 2
fi
if ! [[ "$SLOT_POLL_SEC" =~ ^[0-9]+$ ]] || [[ "$SLOT_POLL_SEC" -lt 1 ]]; then
  echo "QUEUE_XSEC_RESCUE_SLOT_POLL_SEC must be a positive integer" >&2
  exit 2
fi
if ! [[ "$MAX_PARALLEL_FACTORY" =~ ^[0-9]+$ ]] || [[ "$MAX_PARALLEL_FACTORY" -lt 1 ]]; then
  echo "QUEUE_XSEC_RESCUE_MAX_PARALLEL_FACTORY must be an integer >= 1" >&2
  exit 2
fi
if ! [[ "$REFRESH_TOP_K" =~ ^[0-9]+$ ]] || [[ "$REFRESH_TOP_K" -lt 1 ]]; then
  echo "--refresh-top-k must be a positive integer" >&2
  exit 2
fi
if ! [[ "$REFRESH_BUDGET_PER_SEED" =~ ^[0-9]+$ ]] || [[ "$REFRESH_BUDGET_PER_SEED" -lt 1 ]]; then
  echo "--refresh-budget-per-seed must be a positive integer" >&2
  exit 2
fi

python_factory_count() {
  python3 - <<'PY'
import subprocess

try:
    rows = subprocess.check_output(["ps", "-eo", "comm,args"], text=True)
except Exception:
    print(0)
    raise SystemExit
count = 0
for line in rows.splitlines()[1:]:
    parts = line.strip().split(maxsplit=1)
    if len(parts) != 2:
        continue
    comm, args = parts
    if comm == "python3" and "-m v9.contract.xsec_ohlcv_factory" in args:
        count += 1
print(count)
PY
}

parent_is_accepted() {
  python3 - "$PARENT_OUTPUT_JSON" <<'PY'
import json
import sys

with open(sys.argv[1]) as handle:
    payload = json.load(handle)
accepted = bool((payload.get("summary") or {}).get("accepted_train_only"))
print(f"parent_accepted_train_only={accepted}")
raise SystemExit(0 if accepted else 1)
PY
}

config_list_fingerprint() {
  python3 - "$CONFIG_LIST_JSON" <<'PY'
import hashlib
import pathlib
import sys

print(hashlib.sha1(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())
PY
}

parent_effective_trials() {
  python3 - "$PARENT_OUTPUT_JSON" <<'PY'
import json
import sys

with open(sys.argv[1]) as handle:
    payload = json.load(handle)

selection_validation = payload.get("selection_validation") or {}
summary = payload.get("summary") or {}
for value in (
    selection_validation.get("effective_trials"),
    payload.get("effective_trials"),
    summary.get("effective_trials"),
):
    if value is not None:
        print(max(1, int(value or 0)))
        raise SystemExit

prior = selection_validation.get("prior_trials")
n_configs = selection_validation.get("n_configs_tested") or selection_validation.get("n_configs")
if prior is None:
    prior = payload.get("prior_trials") or summary.get("prior_trials")
if n_configs is None:
    n_configs = payload.get("n_configs_tested") or summary.get("n_configs_tested") or summary.get("rows")
print(max(1, int(prior or 0) + int(n_configs or 0)))
PY
}

refresh_rescue_configs_from_parent() {
  local plan_json="$REFRESH_PLAN_JSON"
  if [[ -z "$plan_json" ]]; then
    plan_json="${CONFIG_LIST_JSON%.json}_plan.json"
  fi
  mkdir -p "$(dirname "$plan_json")" "$(dirname "$CONFIG_LIST_JSON")"
  local tmp_plan="${plan_json}.tmp.$$"
  local tmp_configs="${CONFIG_LIST_JSON}.tmp.$$"
  python3 scripts/v9_xsec_rescue_plan.py "$PARENT_OUTPUT_JSON" \
    --top-k "$REFRESH_TOP_K" \
    --budget-per-seed "$REFRESH_BUDGET_PER_SEED" \
    --out-plan "$tmp_plan" \
    --out-configs "$tmp_configs"
  mv "$tmp_plan" "$plan_json"
  mv "$tmp_configs" "$CONFIG_LIST_JSON"
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) refreshed_rescue_from_parent configs=$CONFIG_LIST_JSON plan=$plan_json"
}

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) waiting_for_parent $PARENT_OUTPUT_JSON"
while [[ ! -s "$PARENT_OUTPUT_JSON" ]]; do
  sleep "$POLL_SEC"
done

if parent_is_accepted; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) parent accepted; skipping rescue"
  exit 0
fi

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) parent did not accept; queueing rescue configs=$CONFIG_LIST_JSON"
if [[ "$REFRESH_BEFORE_RUN" == "1" ]]; then
  refresh_rescue_configs_from_parent
fi
while true; do
  active_factory_count="$(python_factory_count)"
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) python_factory_count=$active_factory_count waiting_for_slot max=$MAX_PARALLEL_FACTORY"
  if [[ "$active_factory_count" -lt "$MAX_PARALLEL_FACTORY" ]]; then
    break
  fi
  sleep "$SLOT_POLL_SEC"
done

EFFECTIVE_FINGERPRINT="$FINGERPRINT"
if [[ "$EFFECTIVE_FINGERPRINT" == "auto" ]]; then
  EFFECTIVE_FINGERPRINT="$(config_list_fingerprint)"
fi
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) rescue_fingerprint=$EFFECTIVE_FINGERPRINT"

EFFECTIVE_PRIOR_TRIALS="$PRIOR_TRIALS"
if [[ "$EFFECTIVE_PRIOR_TRIALS" == "auto" ]]; then
  EFFECTIVE_PRIOR_TRIALS="$(parent_effective_trials)"
fi
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) rescue_prior_trials=$EFFECTIVE_PRIOR_TRIALS"

TRAIN_ONLY_ARTIFACT_COMMAND_TIMEOUT_SEC="${TRAIN_ONLY_ARTIFACT_COMMAND_TIMEOUT_SEC:-14400}" \
TRAIN_ONLY_ARTIFACT_MAX_RUNTIME_SEC="${TRAIN_ONLY_ARTIFACT_MAX_RUNTIME_SEC:-57600}" \
TRAIN_ONLY_ARTIFACT_POLL_SEC="${TRAIN_ONLY_ARTIFACT_POLL_SEC:-60}" \
  ./scripts/train_only_artifact_keeper_loop.sh --output-json "$OUTPUT_JSON" -- \
  nice -n "$NICE_LEVEL" python3 -m v9.contract.xsec_ohlcv_factory \
    --data-snapshot "$DATA_SNAPSHOT" \
    --preset "$PRESET" \
    --config-list-json "$CONFIG_LIST_JSON" \
    --train-start "$TRAIN_START" \
    --train-end "$TRAIN_END" \
    --embargo-start "$EMBARGO_START" \
    --bootstrap-iterations "$BOOTSTRAP_ITERATIONS" \
    --prior-trials "$EFFECTIVE_PRIOR_TRIALS" \
    --out-json "$OUTPUT_JSON" \
    --out-md "$OUTPUT_MD"

python3 scripts/v9_ingest_train_only_artifact.py \
  --task-name "$TASK_NAME" \
  --preset "$PRESET" \
  --fingerprint "$EFFECTIVE_FINGERPRINT" \
  --train-start "$TRAIN_START" \
  --train-end "$TRAIN_END" \
  --embargo-start "$EMBARGO_START" \
  --bootstrap-iterations "$BOOTSTRAP_ITERATIONS" \
  --prior-trials "$EFFECTIVE_PRIOR_TRIALS" \
  --output-json "$OUTPUT_JSON" \
  --output-md "$OUTPUT_MD" \
  --report-json "$REPORT_JSON" \
  --force
