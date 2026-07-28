#!/usr/bin/env bash
set -euo pipefail

KEEPER_SESSION="${1:-v9_train_only_keeper}"
TARGET_SESSION="${TRAIN_ONLY_TARGET_SESSION:-v9_auto_research_continuous}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/logs/v9_auto_research"
LOG="$LOG_DIR/train_only_keeper_$(date -u +%Y%m%dT%H%M%SZ).log"
KEEPER_FORCE_RESTART="${TRAIN_ONLY_KEEPER_FORCE_RESTART:-0}"
KEEPER_MAX_PYTHON_FACTORY="${TRAIN_ONLY_KEEPER_MAX_PYTHON_FACTORY:-0}"
KEEPER_INTERVAL_SEC="${TRAIN_ONLY_KEEPER_INTERVAL_SEC:-600}"
KEEPER_STOP_POLL_SEC="${TRAIN_ONLY_KEEPER_STOP_POLL_SEC:-30}"

if [[ "$KEEPER_SESSION" == -* || "$TARGET_SESSION" == -* ]]; then
  echo "session names must not start with '-'" >&2
  exit 2
fi

if [[ "$KEEPER_SESSION" == "$TARGET_SESSION" ]]; then
  echo "keeper session and target session must be different" >&2
  exit 2
fi

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux is required" >&2
  exit 2
fi

cd "$ROOT"
bash -n scripts/train_only_keeper_loop.sh
mkdir -p "$LOG_DIR" state control
find "$LOG_DIR" -maxdepth 1 -name 'train_only_keeper_*.log' -mtime +14 -delete 2>/dev/null || true

if tmux has-session -t "=$KEEPER_SESSION" 2>/dev/null; then
  echo "tmux session already exists: $KEEPER_SESSION"
  exit 0
fi

printf -v ROOT_Q "%q" "$ROOT"
printf -v LOG_Q "%q" "$LOG"
printf -v TARGET_SESSION_Q "%q" "$TARGET_SESSION"
printf -v KEEPER_FORCE_RESTART_Q "%q" "$KEEPER_FORCE_RESTART"
printf -v KEEPER_MAX_PYTHON_FACTORY_Q "%q" "$KEEPER_MAX_PYTHON_FACTORY"
printf -v KEEPER_INTERVAL_SEC_Q "%q" "$KEEPER_INTERVAL_SEC"
printf -v KEEPER_STOP_POLL_SEC_Q "%q" "$KEEPER_STOP_POLL_SEC"
tmux new-session -d -s "$KEEPER_SESSION" \
  "cd $ROOT_Q && TRAIN_ONLY_SESSION=$TARGET_SESSION_Q TRAIN_ONLY_KEEPER_FORCE_RESTART=$KEEPER_FORCE_RESTART_Q TRAIN_ONLY_KEEPER_MAX_PYTHON_FACTORY=$KEEPER_MAX_PYTHON_FACTORY_Q TRAIN_ONLY_KEEPER_INTERVAL_SEC=$KEEPER_INTERVAL_SEC_Q TRAIN_ONLY_KEEPER_STOP_POLL_SEC=$KEEPER_STOP_POLL_SEC_Q ./scripts/train_only_keeper_loop.sh >> $LOG_Q 2>&1"

echo "started train-only keeper: $KEEPER_SESSION"
echo "target session: $TARGET_SESSION"
echo "log: $LOG"
echo "force_restart: $KEEPER_FORCE_RESTART"
echo "max_python_factory: $KEEPER_MAX_PYTHON_FACTORY"
