#!/usr/bin/env bash
set -euo pipefail

SESSION="${1:-v9_revalidation_keeper}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/logs/v9_revalidation"
LOG="$LOG_DIR/keeper_$(date -u +%Y%m%dT%H%M%SZ).log"

if [[ "$SESSION" == -* ]]; then
  echo "session name must not start with '-'" >&2
  exit 2
fi

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux is required" >&2
  exit 2
fi

cd "$ROOT"
bash -n scripts/revalidation_keeper_loop.sh
mkdir -p "$LOG_DIR" artifacts/v9/revalidation control
find "$LOG_DIR" -maxdepth 1 -name 'keeper_*.log' -mtime +14 -delete 2>/dev/null || true

if tmux has-session -t "=$SESSION" 2>/dev/null; then
  echo "tmux session already exists: $SESSION"
  exit 0
fi

printf -v ROOT_Q "%q" "$ROOT"
printf -v LOG_Q "%q" "$LOG"
tmux new-session -d -s "$SESSION" \
  "cd $ROOT_Q && ./scripts/revalidation_keeper_loop.sh >> $LOG_Q 2>&1"

echo "started revalidation keeper: $SESSION"
echo "log: $LOG"
