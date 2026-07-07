#!/usr/bin/env bash
set -euo pipefail

SESSION="${1:-v9_auto_research}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/logs/v9_auto_research"
LOG="$LOG_DIR/runner_$(date -u +%Y%m%dT%H%M%SZ).log"
TARGET_DISTINCT_CANDIDATES="${TARGET_DISTINCT_CANDIDATES:-8}"
PLANNER_BATCH_SIZE="${PLANNER_BATCH_SIZE:-3}"
MAX_CYCLES="${MAX_CYCLES:-0}"
MAX_HOURS="${MAX_HOURS:-0}"
CYCLE_SLEEP_SEC="${CYCLE_SLEEP_SEC:-60}"

if [[ "$SESSION" == -* ]]; then
  echo "session name must not start with '-'" >&2
  exit 2
fi

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux is required" >&2
  exit 2
fi

cd "$ROOT"
python3 -m v9.contract.auto_research --help >/dev/null
mkdir -p "$LOG_DIR" state

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "tmux session already exists: $SESSION"
  exit 0
fi

printf -v ROOT_Q "%q" "$ROOT"
printf -v LOG_Q "%q" "$LOG"
tmux new-session -d -s "$SESSION" \
  "cd $ROOT_Q && python3 -m v9.contract.auto_research --mode continuous --continue-after-candidate --target-distinct-candidates $TARGET_DISTINCT_CANDIDATES --planner-batch-size $PLANNER_BATCH_SIZE --max-cycles $MAX_CYCLES --max-hours $MAX_HOURS --cycle-sleep-sec $CYCLE_SLEEP_SEC >> $LOG_Q 2>&1"

echo "started train-only auto research: $SESSION"
echo "log: $LOG"
