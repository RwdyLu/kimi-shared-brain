#!/usr/bin/env bash
set -euo pipefail

PRESET="${1:-}"
TASK_SUFFIX="${2:-$(date -u +%Y%m%dT%H%M%SZ)}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat >&2 <<'EOF'
usage: start_xsec_supplemental_preset.sh PRESET [TASK_SUFFIX]

Starts a supplemental train-only XSEC OHLCV preset in tmux, guarded by a
maximum active-factory count. The task writes a normal train-only artifact,
then ingests it into the candidate ledgers. It does not authorize paper/live.

Environment:
  MAX_PARALLEL_FACTORY        default: 2
  NICE_LEVEL                  default: 10
  PRIOR_TRIALS                default: auto
  START_HIT_MONITOR           default: 1
  WAIT_FOR_SLOT               default: 0
  SLOT_POLL_SEC               default: 300
  DATA_SNAPSHOT               default: full 2017-08..2024-06 snapshot
  TRAIN_START                 default: 2017-08-01
  TRAIN_END                   default: 2024-06-30 23:59:59
  EMBARGO_START               default: 2024-07-01
  BOOTSTRAP_ITERATIONS        default: 100
EOF
}

if [[ -z "$PRESET" || "$PRESET" == "-h" || "$PRESET" == "--help" ]]; then
  usage
  exit 2
fi
if [[ "$PRESET" == -* || "$TASK_SUFFIX" == -* ]]; then
  echo "PRESET and TASK_SUFFIX must not start with '-'" >&2
  exit 2
fi
if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux is required" >&2
  exit 2
fi

cd "$ROOT"

MAX_PARALLEL_FACTORY="${MAX_PARALLEL_FACTORY:-2}"
NICE_LEVEL="${NICE_LEVEL:-10}"
PRIOR_TRIALS="${PRIOR_TRIALS:-auto}"
START_HIT_MONITOR="${START_HIT_MONITOR:-1}"
WAIT_FOR_SLOT="${WAIT_FOR_SLOT:-0}"
SLOT_POLL_SEC="${SLOT_POLL_SEC:-300}"
TRAIN_START="${TRAIN_START:-2017-08-01}"
TRAIN_END="${TRAIN_END:-2024-06-30 23:59:59}"
EMBARGO_START="${EMBARGO_START:-2024-07-01}"
BOOTSTRAP_ITERATIONS="${BOOTSTRAP_ITERATIONS:-100}"
DATA_SNAPSHOT="${DATA_SNAPSHOT:-artifacts/v9/data_snapshots/xsec_ohlcv_2017_08_01_2024_06_30_23_59_59_2024_07_01_5b60e9a9f3_958ac849fb867a34.parquet}"

for pair in "MAX_PARALLEL_FACTORY:$MAX_PARALLEL_FACTORY" "NICE_LEVEL:$NICE_LEVEL" "BOOTSTRAP_ITERATIONS:$BOOTSTRAP_ITERATIONS" "SLOT_POLL_SEC:$SLOT_POLL_SEC"; do
  name="${pair%%:*}"
  value="${pair#*:}"
  if ! [[ "$value" =~ ^-?[0-9]+$ ]]; then
    echo "$name must be an integer" >&2
    exit 2
  fi
done
if [[ "$MAX_PARALLEL_FACTORY" -lt 1 ]]; then
  echo "MAX_PARALLEL_FACTORY must be >= 1" >&2
  exit 2
fi
if [[ "$SLOT_POLL_SEC" -lt 1 ]]; then
  echo "SLOT_POLL_SEC must be >= 1" >&2
  exit 2
fi
if [[ "$WAIT_FOR_SLOT" != "0" && "$WAIT_FOR_SLOT" != "1" ]]; then
  echo "WAIT_FOR_SLOT must be 0 or 1" >&2
  exit 2
fi

active_factory_count() {
  ps -eo comm,args | awk '$1=="python3" && $0 ~ /-m v9[.]contract[.]xsec_ohlcv_factory/ {count++} END {print count + 0}'
}

auto_prior_trials() {
  python3 - <<'PY'
import json
import pathlib

values = []

def add(value):
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return
    if number > 0:
        values.append(number)

for path in pathlib.Path("state").glob("*.jsonl"):
    try:
        lines = path.read_text().splitlines()
    except OSError:
        continue
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        add(row.get("effective_trials"))
        add(row.get("prior_trials"))

for path in pathlib.Path("artifacts/v9/contract_lab").glob("*.progress.meta.json"):
    try:
        row = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        continue
    add(row.get("effective_trials"))
    add(int(row.get("prior_trials") or 0) + int(row.get("completed_rows") or 0))

for path in pathlib.Path("artifacts/v9/contract_lab").glob("*.json"):
    try:
        row = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        continue
    selection = row.get("selection_validation") or {}
    summary = row.get("summary") or {}
    add(selection.get("effective_trials"))
    add(row.get("effective_trials"))
    add(summary.get("effective_trials"))
    if selection:
        add(int(selection.get("prior_trials") or 0) + int(selection.get("n_configs_tested") or selection.get("n_configs") or 0))
    add(int(row.get("prior_trials") or summary.get("prior_trials") or 0) + int(row.get("n_configs_tested") or summary.get("n_configs_tested") or summary.get("rows") or 0))

print(max(values) if values else 1)
PY
}

EFFECTIVE_PRIOR_TRIALS="$PRIOR_TRIALS"
if [[ "$EFFECTIVE_PRIOR_TRIALS" == "auto" ]]; then
  EFFECTIVE_PRIOR_TRIALS="$(auto_prior_trials)"
fi
if ! [[ "$EFFECTIVE_PRIOR_TRIALS" =~ ^[0-9]+$ ]] || [[ "$EFFECTIVE_PRIOR_TRIALS" -lt 1 ]]; then
  echo "PRIOR_TRIALS must be a positive integer or auto" >&2
  exit 2
fi

TASK="xsec_ohlcv_${PRESET}_${TASK_SUFFIX}"
SESSION="v9_${PRESET}_${TASK_SUFFIX}"
MONITOR_SESSION="v9_xsec_hit_monitor_${PRESET}_${TASK_SUFFIX}"
OUT="artifacts/v9/contract_lab/${TASK}.json"
MD="artifacts/v9/contract_lab/${TASK}.md"
REPORT="state/v9_ingest_${TASK}.json"
LOG="logs/v9_auto_research/${TASK}.log"
PROGRESS="${OUT%.json}.progress.jsonl"
HIT_JSON="state/xsec_rescue_hit_monitor_${PRESET}_${TASK_SUFFIX}.json"
HIT_TEXT="state/xsec_rescue_hit_monitor_${PRESET}_${TASK_SUFFIX}.txt"
HIT_LOG="logs/v9_auto_research/xsec_hit_monitor_${PRESET}_${TASK_SUFFIX}.log"

if [[ -s "$OUT" ]]; then
  echo "artifact exists: $OUT"
  exit 0
fi
if tmux has-session -t "=$SESSION" 2>/dev/null; then
  echo "tmux session already exists: $SESSION"
  exit 0
fi

while true; do
  count="$(active_factory_count)"
  echo "active_factory_count=$count max=$MAX_PARALLEL_FACTORY"
  if [[ "$count" -lt "$MAX_PARALLEL_FACTORY" ]]; then
    break
  fi
  if [[ "$WAIT_FOR_SLOT" != "1" ]]; then
    echo "not starting: active factory limit reached"
    exit 0
  fi
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) waiting_for_slot sleep=${SLOT_POLL_SEC}s"
  sleep "$SLOT_POLL_SEC"
done

mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")" "$(dirname "$LOG")"

printf -v OUT_Q "%q" "$OUT"
printf -v MD_Q "%q" "$MD"
printf -v REPORT_Q "%q" "$REPORT"
printf -v LOG_Q "%q" "$LOG"
printf -v DATA_SNAPSHOT_Q "%q" "$DATA_SNAPSHOT"
printf -v PRESET_Q "%q" "$PRESET"
printf -v TASK_Q "%q" "$TASK"
printf -v TRAIN_START_Q "%q" "$TRAIN_START"
printf -v TRAIN_END_Q "%q" "$TRAIN_END"
printf -v EMBARGO_START_Q "%q" "$EMBARGO_START"
printf -v ROOT_Q "%q" "$ROOT"

tmux new-session -d -s "$SESSION" \
  "cd $ROOT_Q && { echo \"\$(date -u +%Y-%m-%dT%H:%M:%SZ) start $TASK_Q prior_trials=$EFFECTIVE_PRIOR_TRIALS\"; TRAIN_ONLY_ARTIFACT_COMMAND_TIMEOUT_SEC=14400 TRAIN_ONLY_ARTIFACT_MAX_RUNTIME_SEC=57600 TRAIN_ONLY_ARTIFACT_POLL_SEC=60 ./scripts/train_only_artifact_keeper_loop.sh --output-json $OUT_Q -- nice -n $NICE_LEVEL python3 -m v9.contract.xsec_ohlcv_factory --data-snapshot $DATA_SNAPSHOT_Q --preset $PRESET_Q --train-start $TRAIN_START_Q --train-end $TRAIN_END_Q --embargo-start $EMBARGO_START_Q --bootstrap-iterations $BOOTSTRAP_ITERATIONS --prior-trials $EFFECTIVE_PRIOR_TRIALS --out-json $OUT_Q --out-md $MD_Q && python3 scripts/v9_ingest_train_only_artifact.py --task-name $TASK_Q --preset $PRESET_Q --train-start $TRAIN_START_Q --train-end $TRAIN_END_Q --embargo-start $EMBARGO_START_Q --bootstrap-iterations $BOOTSTRAP_ITERATIONS --prior-trials $EFFECTIVE_PRIOR_TRIALS --output-json $OUT_Q --output-md $MD_Q --report-json $REPORT_Q --force; } >> $LOG_Q 2>&1"

echo "started $SESSION"
echo "task=$TASK"
echo "prior_trials=$EFFECTIVE_PRIOR_TRIALS"
echo "out=$OUT"
echo "log=$LOG"

if [[ "$START_HIT_MONITOR" == "1" ]]; then
  mkdir -p "$(dirname "$HIT_JSON")" "$(dirname "$HIT_LOG")"
  printf -v PROGRESS_Q "%q" "$PROGRESS"
  printf -v HIT_JSON_Q "%q" "$HIT_JSON"
  printf -v HIT_TEXT_Q "%q" "$HIT_TEXT"
  printf -v HIT_LOG_Q "%q" "$HIT_LOG"
  if ! tmux has-session -t "=$MONITOR_SESSION" 2>/dev/null; then
    tmux new-session -d -s "$MONITOR_SESSION" \
      "cd $ROOT_Q && python3 scripts/v9_xsec_rescue_hit_monitor.py $PROGRESS_Q --out-json $HIT_JSON_Q --out-text $HIT_TEXT_Q --top-limit 5 --loop --sleep-sec 300 >> $HIT_LOG_Q 2>&1"
    echo "started monitor $MONITOR_SESSION"
  fi
fi
