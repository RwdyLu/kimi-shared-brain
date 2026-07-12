#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION="${TRAIN_ONLY_SESSION:-v9_auto_research_continuous}"
INTERVAL_SEC="${TRAIN_ONLY_KEEPER_INTERVAL_SEC:-600}"
STOP_POLL_SEC="${TRAIN_ONLY_KEEPER_STOP_POLL_SEC:-30}"
CONTROL_DIR="${TRAIN_ONLY_CONTROL_DIR:-control}"
RUN_ONCE="${TRAIN_ONLY_KEEPER_ONCE:-0}"

if [[ "$SESSION" == -* ]]; then
  echo "session name must not start with '-'" >&2
  exit 2
fi
if ! [[ "$INTERVAL_SEC" =~ ^[0-9]+$ ]] || [[ "$INTERVAL_SEC" -lt 30 ]]; then
  echo "TRAIN_ONLY_KEEPER_INTERVAL_SEC must be an integer >= 30" >&2
  exit 2
fi
if ! [[ "$STOP_POLL_SEC" =~ ^[0-9]+$ ]] || [[ "$STOP_POLL_SEC" -lt 1 ]]; then
  echo "TRAIN_ONLY_KEEPER_STOP_POLL_SEC must be an integer >= 1" >&2
  exit 2
fi

cd "$ROOT"
mkdir -p "$CONTROL_DIR" logs/v9_auto_research state

sleep_with_stop_poll() {
  local remaining="$INTERVAL_SEC"
  local step
  while [[ "$remaining" -gt 0 ]]; do
    if [[ -e "$CONTROL_DIR/STOP" ]]; then
      echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) stop requested during sleep: $CONTROL_DIR/STOP"
      exit 0
    fi
    step="$STOP_POLL_SEC"
    if [[ "$step" -gt "$remaining" ]]; then
      step="$remaining"
    fi
    sleep "$step"
    remaining=$((remaining - step))
  done
}

echo "train-only keeper loop starting"
echo "session=$SESSION interval_sec=$INTERVAL_SEC"

while true; do
  if [[ -e "$CONTROL_DIR/STOP" ]]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) stop requested: $CONTROL_DIR/STOP"
    exit 0
  fi

  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ensuring train-only auto research"
  if ! ./scripts/ensure_train_only_running.sh "$SESSION"; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ensure_train_only_running failed"
  fi

  if [[ "$RUN_ONCE" == "1" ]]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) run-once complete"
    exit 0
  fi

  sleep_with_stop_poll
done
