#!/usr/bin/env bash
set -euo pipefail

SESSION="${1:-v9_revalidation_next_runnable}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STOP="$ROOT/control/STOP"

cd "$ROOT"
mkdir -p artifacts/v9/revalidation control logs/v9_revalidation

if [[ -e "$STOP" ]]; then
  echo "not starting: control/STOP exists"
  exit 0
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "already running: $SESSION"
  exit 0
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
tmux new-session -d -s "$SESSION" \
  "cd '$ROOT' && python3 scripts/v9_revalidation_runner.py --plan artifacts/v9/revalidation/v9_candidate_revalidation_plan.json --runner-state artifacts/v9/revalidation/runner_state.json --max-groups 1 --next-runnable --out-json artifacts/v9/revalidation/last_next_runnable_report.json --format text >> logs/v9_revalidation/next_runnable_${stamp}.log 2>&1"
echo "started: $SESSION"
