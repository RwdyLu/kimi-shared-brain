#!/usr/bin/env bash
set -euo pipefail

SESSION="${1:-v9_auto_research_continuous}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="$ROOT/state/v9_auto_research_state.json"
STOP="$ROOT/control/STOP"
FORCE_RESTART="${FORCE_RESTART:-0}"
STALE_SEC="${STALE_SEC:-300}"

cd "$ROOT"
mkdir -p control logs/v9_auto_research state

if [[ -e "$STOP" ]]; then
  echo "not starting: control/STOP exists"
  exit 0
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
  if [[ -f "$STATE" ]]; then
    now="$(date +%s)"
    mtime="$(stat -c %Y "$STATE")"
    age="$((now - mtime))"
    if (( age > STALE_SEC )) && ! pgrep -f "v9.contract.xsec_ohlcv_factory" >/dev/null 2>&1; then
      echo "restarting stale session: $SESSION state_age_sec=$age"
      tmux kill-session -t "$SESSION" 2>/dev/null || true
      sleep 2
    else
      echo "already running: $SESSION state_age_sec=$age"
      exit 0
    fi
  else
    echo "already running: $SESSION"
    exit 0
  fi
fi

reason="$(
  python3 - <<'PY'
import json, pathlib
p = pathlib.Path("state/v9_auto_research_state.json")
if not p.exists():
    print("")
else:
    try:
        j = json.loads(p.read_text())
    except Exception:
        print("")
    else:
        print(j.get("stop_reason") or j.get("reason") or "")
PY
)"

case "$reason" in
  disk_guard|failure_fuse|budget_exhausted:*)
    if [[ "$FORCE_RESTART" != "1" ]]; then
      echo "not starting: safety stop_reason=$reason"
      exit 2
    fi
    ;;
esac

./scripts/start_train_only.sh "$SESSION"
