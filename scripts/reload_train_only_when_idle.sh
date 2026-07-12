#!/usr/bin/env bash
set -euo pipefail

SESSION="${1:-v9_auto_research_continuous}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POLL_SEC="${AUTO_RELOAD_POLL_SEC:-60}"
TIMEOUT_SEC="${AUTO_RELOAD_TIMEOUT_SEC:-21600}"
DRY_RUN="${AUTO_RELOAD_DRY_RUN:-0}"

if [[ "$SESSION" == -* ]]; then
  echo "session name must not start with '-'" >&2
  exit 2
fi
if ! [[ "$POLL_SEC" =~ ^[0-9]+$ ]] || [[ "$POLL_SEC" -lt 1 ]]; then
  echo "AUTO_RELOAD_POLL_SEC must be an integer >= 1" >&2
  exit 2
fi
if ! [[ "$TIMEOUT_SEC" =~ ^[0-9]+$ ]] || [[ "$TIMEOUT_SEC" -lt 1 ]]; then
  echo "AUTO_RELOAD_TIMEOUT_SEC must be an integer >= 1" >&2
  exit 2
fi

cd "$ROOT"
START_TS="$(date +%s)"

auto_pids() {
  pgrep -f "^python3 -m v9[.]contract[.]auto_research .*--mode continuous" || true
}

direct_train_child_count() {
  local pid="$1"
  ps --ppid "$pid" -o cmd= 2>/dev/null \
    | grep -Ec "python3 -m v9[.]contract[.](xsec_ohlcv_factory|tsmom_factory)" || true
}

reload_session() {
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) dry-run: would reload $SESSION"
    return 0
  fi
  if tmux has-session -t "=$SESSION" 2>/dev/null; then
    tmux kill-session -t "=$SESSION"
    sleep 2
  fi
  ./scripts/start_train_only.sh "$SESSION"
}

while true; do
  now="$(date +%s)"
  elapsed=$((now - START_TS))
  if [[ "$elapsed" -ge "$TIMEOUT_SEC" ]]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) timeout waiting for idle auto research session: $SESSION" >&2
    exit 124
  fi

  if ! tmux has-session -t "=$SESSION" 2>/dev/null; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) session absent; starting latest auto research: $SESSION"
    reload_session
    exit 0
  fi

  pids="$(auto_pids)"
  if [[ -z "$pids" ]]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) no auto process found; reloading session: $SESSION"
    reload_session
    exit 0
  fi

  busy_children=0
  for pid in $pids; do
    busy_children=$((busy_children + $(direct_train_child_count "$pid")))
  done
  if [[ "$busy_children" -eq 0 ]]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) auto process idle; reloading latest code for $SESSION"
    reload_session
    exit 0
  fi

  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) waiting for auto idle: session=$SESSION auto_pids=$(echo "$pids" | tr '\n' ',') direct_train_children=$busy_children elapsed=${elapsed}s"
  sleep "$POLL_SEC"
done
