#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PAPER_SESSION="${PAPER_SESSION:-xsec_paper_shadow}"
GATE_SESSION="${GATE_SESSION:-xsec_live_canary_gate}"
PAPER_SLEEP_SEC="${PAPER_SLEEP_SEC:-1800}"
GATE_SLEEP_SEC="${GATE_SLEEP_SEC:-3600}"
LOG_DIR="$ROOT/logs"
PAPER_LOG="$LOG_DIR/xsec_paper_shadow.log"
GATE_LOG="$LOG_DIR/xsec_live_canary_gate.log"

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux is required" >&2
  exit 2
fi

cd "$ROOT"
python3 scripts/v9_xsec_paper_shadow.py --help >/dev/null
python3 scripts/v9_xsec_live_canary_readiness_gate.py --help >/dev/null
mkdir -p "$LOG_DIR" state artifacts/v9/paper

if [[ ! -f state/xsec_paper_readiness_gate_state.json ]]; then
  echo "missing state/xsec_paper_readiness_gate_state.json; run paper readiness gate first" >&2
  exit 2
fi

if ! tmux has-session -t "$PAPER_SESSION" 2>/dev/null; then
  printf -v ROOT_Q "%q" "$ROOT"
  printf -v PAPER_LOG_Q "%q" "$PAPER_LOG"
  tmux new-session -d -s "$PAPER_SESSION" \
    "cd $ROOT_Q && python3 scripts/v9_xsec_paper_shadow.py --loop --sleep-sec $PAPER_SLEEP_SEC >> $PAPER_LOG_Q 2>&1"
  echo "started paper shadow: $PAPER_SESSION"
else
  echo "paper shadow already running: $PAPER_SESSION"
fi

if ! tmux has-session -t "$GATE_SESSION" 2>/dev/null; then
  printf -v GATE_LOG_Q "%q" "$GATE_LOG"
  tmux new-session -d -s "$GATE_SESSION" \
    "cd $ROOT_Q && while true; do python3 scripts/v9_xsec_live_canary_readiness_gate.py --format text >> $GATE_LOG_Q 2>&1; sleep $GATE_SLEEP_SEC; done"
  echo "started live-canary gate monitor: $GATE_SESSION"
else
  echo "live-canary gate monitor already running: $GATE_SESSION"
fi

echo "paper log: $PAPER_LOG"
echo "gate log: $GATE_LOG"
