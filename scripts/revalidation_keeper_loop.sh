#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER_SESSION="${REVALIDATION_RUNNER_SESSION:-v9_revalidation_next_runnable}"
INTERVAL_SEC="${REVALIDATION_KEEPER_INTERVAL_SEC:-600}"
STATUS_GROUPS="${REVALIDATION_KEEPER_STATUS_GROUPS:-5}"
COMMAND_TIMEOUT_SEC="${REVALIDATION_KEEPER_COMMAND_TIMEOUT_SEC:-120}"
STOP_POLL_SEC="${REVALIDATION_KEEPER_STOP_POLL_SEC:-30}"
HOLDOUT_AUDITOR_ENABLED="${REVALIDATION_HOLDOUT_AUDITOR_ENABLED:-1}"
HOLDOUT_AUDITOR_TIMEOUT_SEC="${REVALIDATION_HOLDOUT_AUDITOR_TIMEOUT_SEC:-900}"
HOLDOUT_AUDITOR_MAX_GROUPS="${REVALIDATION_HOLDOUT_AUDITOR_MAX_GROUPS:-10}"
HOLDOUT_AUDITOR_MAX_CONFIGS="${REVALIDATION_HOLDOUT_AUDITOR_MAX_CONFIGS:-25}"
HOLDOUT_AUDITOR_RECENT_DAYS="${REVALIDATION_HOLDOUT_AUDITOR_RECENT_DAYS:-45}"
PLAN="${REVALIDATION_PLAN:-artifacts/v9/revalidation/v9_candidate_revalidation_plan.json}"
RUNNER_STATE="${REVALIDATION_RUNNER_STATE:-artifacts/v9/revalidation/runner_state.json}"
STATUS_JSON="${REVALIDATION_KEEPER_STATUS_JSON:-artifacts/v9/revalidation/keeper_status_report.json}"
HEARTBEAT_JSON="${REVALIDATION_KEEPER_HEARTBEAT_JSON:-artifacts/v9/revalidation/keeper_heartbeat.json}"
HOLDOUT_AUDITOR_JSON="${REVALIDATION_HOLDOUT_AUDITOR_JSON:-artifacts/v9/revalidation/holdout_auditor_report.json}"
CONTROL_DIR="${REVALIDATION_CONTROL_DIR:-control}"
RUN_ONCE="${REVALIDATION_KEEPER_ONCE:-0}"

if [[ "$RUNNER_SESSION" == -* ]]; then
  echo "runner session name must not start with '-'" >&2
  exit 2
fi

if ! [[ "$INTERVAL_SEC" =~ ^[0-9]+$ ]] || [[ "$INTERVAL_SEC" -lt 30 ]]; then
  echo "REVALIDATION_KEEPER_INTERVAL_SEC must be an integer >= 30" >&2
  exit 2
fi

if ! [[ "$COMMAND_TIMEOUT_SEC" =~ ^[0-9]+$ ]] || [[ "$COMMAND_TIMEOUT_SEC" -lt 30 ]]; then
  echo "REVALIDATION_KEEPER_COMMAND_TIMEOUT_SEC must be an integer >= 30" >&2
  exit 2
fi

if ! [[ "$HOLDOUT_AUDITOR_TIMEOUT_SEC" =~ ^[0-9]+$ ]] || [[ "$HOLDOUT_AUDITOR_TIMEOUT_SEC" -lt 60 ]]; then
  echo "REVALIDATION_HOLDOUT_AUDITOR_TIMEOUT_SEC must be an integer >= 60" >&2
  exit 2
fi

if ! [[ "$STOP_POLL_SEC" =~ ^[0-9]+$ ]] || [[ "$STOP_POLL_SEC" -lt 1 ]]; then
  echo "REVALIDATION_KEEPER_STOP_POLL_SEC must be an integer >= 1" >&2
  exit 2
fi

cd "$ROOT"
mkdir -p artifacts/v9/revalidation logs/v9_revalidation "$CONTROL_DIR"

run_with_timeout() {
  local seconds="$1"
  shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "$seconds" "$@"
  else
    "$@"
  fi
}

write_heartbeat() {
  local tmp="${HEARTBEAT_JSON}.tmp.$$"
  cat >"$tmp" <<JSON
{
  "kind": "v9_revalidation_keeper_heartbeat_v1",
  "runner_session": "$RUNNER_SESSION",
  "updated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
JSON
  mv "$tmp" "$HEARTBEAT_JSON"
}

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

echo "revalidation keeper loop starting"
echo "runner_session=$RUNNER_SESSION interval_sec=$INTERVAL_SEC"

while true; do
  if [[ -e "$CONTROL_DIR/STOP" ]]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) stop requested: $CONTROL_DIR/STOP"
    exit 0
  fi

  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ensuring revalidation runner"
  write_heartbeat
  if ! run_with_timeout "$COMMAND_TIMEOUT_SEC" "$ROOT/scripts/ensure_revalidation_running.sh" "$RUNNER_SESSION"; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ensure_revalidation_running failed"
  fi

  status_tmp="${STATUS_JSON}.tmp.$$"
  if run_with_timeout "$COMMAND_TIMEOUT_SEC" python3 "$ROOT/scripts/v9_revalidation_status.py" \
    --plan "$PLAN" \
    --runner-state "$RUNNER_STATE" \
    --max-groups "$STATUS_GROUPS" \
    --include-processes \
    --out-json "$status_tmp" \
    --format text; then
    mv "$status_tmp" "$STATUS_JSON"
  else
    rm -f "$status_tmp"
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) status refresh failed"
  fi

  if [[ "$HOLDOUT_AUDITOR_ENABLED" == "1" && ! -e "$CONTROL_DIR/STOP" ]]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) auditing accepted revalidation holdouts"
    if ! run_with_timeout "$HOLDOUT_AUDITOR_TIMEOUT_SEC" python3 "$ROOT/scripts/v9_revalidation_holdout_auditor.py" \
      --plan "$PLAN" \
      --runner-state "$RUNNER_STATE" \
      --holdout-authorized \
      --skip-existing-any-key \
      --max-groups "$HOLDOUT_AUDITOR_MAX_GROUPS" \
      --max-configs "$HOLDOUT_AUDITOR_MAX_CONFIGS" \
      --recent-days "$HOLDOUT_AUDITOR_RECENT_DAYS" \
      --out-json "$HOLDOUT_AUDITOR_JSON" \
      --format text; then
      echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) holdout auditor failed"
    fi
  fi

  if [[ "$RUN_ONCE" == "1" ]]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) run-once complete"
    exit 0
  fi

  sleep_with_stop_poll
done
